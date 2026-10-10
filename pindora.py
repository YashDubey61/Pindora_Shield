import os
import re
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, AllChem, QED
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit import DataStructs

from Tengan.generate_from_smiles import MoleculeGenerator
from utils.fetch_data import FetchData
from utils.copilot import AzureOpenAIChatClient
from utils.matrix_file import MatrixPredictor

logger = logging.getLogger(__name__)


# ── PAINS filter singleton (loaded once at startup, < 0.5ms per match) ────
_PAINS_PARAMS = FilterCatalogParams()
_PAINS_PARAMS.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
_PAINS_CATALOG = FilterCatalog(_PAINS_PARAMS)


# ── Module-level helper functions (Fix #14: no longer nested) ─────────────

def split_smiles_components(smiles: str) -> list:
    """Split a SMILES string that may contain TenGAN's '$'-delimited
    multi-component notation into individual canonical SMILES.

    NOTE: Standard canonical SMILES use '.' for mixtures; '$' is a
    TenGAN-specific artifact from how the model encodes multi-fragment
    molecules during training on ZINC.
    """
    if not smiles or not isinstance(smiles, str):
        return []

    if '$' in smiles:
        components = smiles.split('$')
    else:
        components = [smiles]

    cleaned = [c.strip() for c in components if c.strip() and len(c.strip()) > 1]
    return cleaned if cleaned else [smiles.strip()]


def calculate_similarity(smiles1: str, smiles2: str) -> float:
    """Tanimoto similarity between two SMILES using Morgan fingerprints (r=2)."""
    try:
        mol1 = Chem.MolFromSmiles(smiles1)
        mol2 = Chem.MolFromSmiles(smiles2)
        if mol1 and mol2:
            fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2)
            fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2)
            return DataStructs.TanimotoSimilarity(fp1, fp2)
    except Exception as e:
        logger.warning("Similarity calculation failed for %s vs %s: %s", smiles1, smiles2, e)
    return 0.0


def check_scaffold_preserved(seed_smiles: str, cand_smiles: str) -> Optional[bool]:
    """Check if Bemis-Murcko core scaffold is preserved between seed and candidate (< 0.2ms)."""
    try:
        s_mol = Chem.MolFromSmiles(seed_smiles)
        c_mol = Chem.MolFromSmiles(cand_smiles)
        if s_mol and c_mol:
            s_scaff = MurckoScaffold.MurckoScaffoldSmiles(mol=s_mol, includeChirality=False)
            c_scaff = MurckoScaffold.MurckoScaffoldSmiles(mol=c_mol, includeChirality=False)
            if not s_scaff:
                return None  # Acyclic seed molecule
            return bool(s_scaff == c_scaff)
    except Exception as e:
        logger.debug("Murcko scaffold check failed: %s", e)
    return None


def get_molecular_properties(smiles: str) -> dict:
    """Compute drug-likeness descriptors via RDKit including QED, SAScore, PAINS, and Lipinski violations."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            mw = Descriptors.MolWt(mol)
            logp = Crippen.MolLogP(mol)
            hbd = Descriptors.NumHDonors(mol)
            hba = Descriptors.NumHAcceptors(mol)
            rot_bonds = Descriptors.NumRotatableBonds(mol)

            # QED (Quantitative Estimate of Drug-likeness, 0.0 – 1.0)
            qed_score = round(QED.qed(mol), 3)

            # Heuristic Synthetic Accessibility via BertzCT complexity (< 0.1ms)
            bertz = Descriptors.BertzCT(mol)
            sascore = round(min(10.0, max(1.0, (bertz / 150.0) + 1.0)), 1)

            # PAINS alert (uses module-level singleton, < 0.5ms)
            pains_alert = _PAINS_CATALOG.HasMatch(mol)

            # Lipinski Rule of 5 violation count (0 to 4)
            lipinski_violations = sum([
                mw > 500,
                logp > 5,
                hbd > 5,
                hba > 10,
            ])

            return {
                "valid": True,
                "molecular_weight": mw,
                "logp": logp,
                "hbd": hbd,
                "hba": hba,
                "rotatable_bonds": rot_bonds,
                "aromatic_rings": Descriptors.NumAromaticRings(mol),
                "qed": qed_score,
                "sascore": sascore,
                "lipinski_violations": lipinski_violations,
                "pains_alert": pains_alert,
            }
    except Exception as e:
        logger.warning("Property calculation failed for %s: %s", smiles, e)
    return {"valid": False}


def _parse_disease_names(raw_json: str) -> List[str]:
    """Robustly extract disease names from LLM JSON output.

    Handles markdown wrapping, the known typo 'desease' (Fix #7),
    and adds schema validation so we don't silently return an empty list.
    """
    cleaned = raw_json.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for disease names: %s", raw_json[:200])
        return []

    # Accept common key variants from the LLM
    diseases = parsed.get("disease") or parsed.get("diseases") or parsed.get("desease", [])

    if not isinstance(diseases, list):
        diseases = [diseases] if diseases else []

    return [d.strip() for d in diseases if isinstance(d, str) and d.strip()]


# ── Main pipeline class ───────────────────────────────────────────────────

class Pindora:
    def __init__(self, matrix_predictor: Optional[MatrixPredictor] = None):
        self.data_processor = FetchData()
        self.copilot = AzureOpenAIChatClient()

        # Fix #3: configurable model path via env
        model_path = os.environ.get(
            "TENGAN_MODEL_PATH",
            "Tengan/res/save_models/ZINC/TenGAN_0.5/rollout_8/batch_64/druglikeness/g_pretrained.pkl"
        )
        self.generator = MoleculeGenerator(
            model_path=model_path,
            batch_size=8,
            max_len=120
        )

        # Fix #11: optional MatriX integration into the pipeline
        self.matrix = matrix_predictor

    def drug_discovery_pipeline(self, prompt: Any) -> List[Dict[str, Any]]:
        # Step 1: LLM → disease names (or reuse pre-parsed list if provided)
        if isinstance(prompt, list):
            diseases = prompt
        else:
            disease_json = self.copilot.generate_disease_name_from_prompt(str(prompt))
            diseases = _parse_disease_names(disease_json)

        if not diseases:
            logger.warning("No diseases resolved from prompt: %s", str(prompt)[:100])
            return []

        logger.info("Resolved diseases: %s", diseases)

        # Step 2-3: Disease → EFO → Targets → Drugs → IC50 + Properties
        max_targets = int(os.environ.get("MAX_TARGETS", "8"))
        max_candidates = int(os.environ.get("MAX_CANDIDATES", "5"))
        samples_per_drug = int(os.environ.get("SAMPLES_PER_DRUG", "3"))

        # Step 2: Resolve candidate target-drug pairs (early-exit when quota reached)
        candidate_items = []
        seen_drugs = set()

        for disease_name in diseases:
            efo_ids = self.data_processor.map_disease_to_efo(disease_name)
            logger.info("Disease: %s -> EFO IDs: %s", disease_name, efo_ids)
            if not efo_ids:
                logger.warning("No EFO ID found for disease: %s", disease_name)
            for efo_id in efo_ids:
                targets = self.data_processor.get_associated_targets(efo_id, max_targets=max_targets)
                for target in targets:
                    drugs = self.data_processor.get_known_drugs_for_target(target["target_id"], max_drugs=10)
                    # Prioritize small molecules or drugs with structural molblock over biologics/oligos
                    sorted_drugs = sorted(
                        drugs,
                        key=lambda d: 0 if (d.get("drug_type") or "").lower() == "small molecule" or d.get("molblock") else 1
                    )
                    for drug in sorted_drugs:
                        did = drug.get("drug_id")
                        if not did or did in seen_drugs:
                            continue
                        seen_drugs.add(did)
                        candidate_items.append((target, drug, disease_name, efo_id))
                        break  # Pick 1 lead drug per target to maximize biological diversity
                    if len(candidate_items) >= max_candidates:
                        break
                if len(candidate_items) >= max_candidates:
                    break
            if len(candidate_items) >= max_candidates:
                break

        # Step 3: Concurrently enrich candidate drugs with IC50 bioactivity and ChEMBL properties
        def _enrich_candidate(item):
            target, drug, dis_name, e_id = item
            d_id = drug["drug_id"]
            try:
                features = self.data_processor.get_molecule_properties(d_id, molblock=drug.get("molblock")) or {}
                if not features.get("smiles"):
                    return None

                ic50_list = []
                try:
                    ic50_list = self.data_processor.get_ic50_data_for_molecule(d_id, limit=50)
                except Exception as ex:
                    logger.warning("IC50 lookup failed for %s (continuing with molecular generation): %s", d_id, ex)

                ic50 = ic50_list[0] if ic50_list else {}
                row = {
                    "disease_name": dis_name,
                    "efo_id": e_id,
                    "target_id": target["target_id"],
                    "target_symbol": target["approved_symbol"],
                    "association_score": target["association_score"],
                    "drug_id": d_id,
                    "drug_name": drug["pref_name"],
                    "clinical_phase": drug["phase"],
                    "ic50_value": ic50.get("standard_value") if ic50 else None,
                    "ic50_units": ic50.get("standard_units") if ic50 else None,
                    "target_chembl_id": ic50.get("target_chembl_id") if ic50 else None,
                    "assay_chembl_id": ic50.get("assay_chembl_id") if ic50 else None,
                    "pchembl_value": ic50.get("pchembl_value") if ic50 else None
                }
                for key, value in features.items():
                    if key != "molecule_chembl_id" and value is not None:
                        row[key] = value
                return row
            except Exception as e:
                logger.warning("Enrichment failed for %s: %s", d_id, e)
                return None

        all_data = []
        if candidate_items:
            with ThreadPoolExecutor(max_workers=min(len(candidate_items), 5)) as pool:
                for row in pool.map(_enrich_candidate, candidate_items):
                    if row is not None:
                        all_data.append(row)

        logger.info("Total records enriched: %d", len(all_data))

        # Step 4: Generate novel molecules via TenGAN
        gen_mol = []
        for rec in all_data:
            input_smiles = rec.get("smiles")
            if not input_smiles:
                # skip records without a canonical SMILES
                continue

            # Fix #8: validate SMILES before sending to generator
            if Chem.MolFromSmiles(input_smiles) is None:
                logger.warning("Skipping invalid SMILES before generation: %s", input_smiles)
                continue

            results = self.generator.generate_from_smiles(input_smiles, samples_per_drug)

            generated_with_props = []
            seen = set()  # Track unique molecules

            for result_smiles in results:
                components = split_smiles_components(result_smiles)

                # Create unique identifier from sorted components
                unique_id = tuple(sorted(components))

                # Skip if already seen (duplicate)
                if unique_id in seen:
                    continue
                seen.add(unique_id)

                component_data = []
                for component in components:
                    props = get_molecular_properties(component)
                    if not props.get("valid"):
                        logger.warning("Skipping chemically invalid generated SMILES: %s", component)
                        continue
                    similarity = calculate_similarity(input_smiles, component)
                    scaffold_preserved = check_scaffold_preserved(input_smiles, component)
                    component_data.append({
                        "smiles": component,
                        "similarity": round(similarity, 3),
                        "scaffold_preserved": scaffold_preserved,
                        "properties": props
                    })

                # append enriched component data
                generated_with_props.append(component_data)

            # Only add if there are unique generated molecules
            if generated_with_props:
                entry: Dict[str, Any] = {
                    "input_smile": input_smiles,
                    "disease_name": rec["disease_name"],
                    "target_symbol": rec["target_symbol"],
                    "drug_name": rec["drug_name"],
                    "generated_molecules": generated_with_props
                }

                # Fix #11: run MatriX predictions inline if available
                if self.matrix is not None:
                    try:
                        predictions = self.matrix.predict_all(input_smiles)
                        entry["predictions"] = predictions
                    except Exception as e:
                        logger.warning("MatriX prediction failed for %s: %s", input_smiles, e)
                        entry["predictions"] = None

                gen_mol.append(entry)

                logger.info("Input: %s (Drug: %s) → %d generated molecules",
                            input_smiles, rec['drug_name'], len(generated_with_props))

        os.makedirs("data", exist_ok=True)
        with open("data/generated_molecules_new.json", "w", encoding="utf-8") as f:
            json.dump(gen_mol, f, indent=2)

        return gen_mol