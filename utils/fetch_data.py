import logging
import time
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# Connection-pooled session for OpenTargets and ChEMBL
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "PindoraShield/1.0 (Biomedical Research Platform; mailto:contact@pindora.ai)",
    "Accept": "application/json",
})
_ADAPTER = HTTPAdapter(pool_connections=25, pool_maxsize=25)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)

OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_URL = "https://www.ebi.ac.uk/chembl/api/data"

def query_open_targets(query: str, variables: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    for attempt in range(max_retries):
        try:
            response = _SESSION.post(OPEN_TARGETS_URL, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            return data
            
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                raise

    raise RuntimeError(f"Open Targets query failed after {max_retries} retries")

def query_chembl(endpoint: str, params: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
    if endpoint.endswith(".json"):
        url = f"{CHEMBL_URL}/{endpoint}"
    else:
        url = f"{CHEMBL_URL}/{endpoint}.json"

    for attempt in range(max_retries):
        try:
            response = _SESSION.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                raise

    raise RuntimeError(f"ChEMBL query failed after {max_retries} retries: {url}")


class FetchData:
    def __init__(self):
        self._efo_cache: Dict[str, List[str]] = {}
        self._props_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    # ============================
    # Step 1: Disease → EFO ID
    # ============================

    def map_disease_to_efo(self, disease_name: str) -> List[str]:
        cache_key = disease_name.strip().lower()
        if cache_key in self._efo_cache:
            return self._efo_cache[cache_key]

        query = """
            query MapIds($terms: [String!]!, $entityNames: [String!]) {
                mapIds(queryTerms: $terms, entityNames: $entityNames) {
                    mappings {
                        term
                        hits {
                            id
                            entity
                        }
                    }
                }
            }
        """
        
        variables = {
            "terms": [disease_name],
            "entityNames": ["disease"]
        }
        
        data = query_open_targets(query, variables)
        efo_ids = []
        
        for mapping in data["data"]["mapIds"]["mappings"]:
            for hit in mapping["hits"]:
                if hit["entity"] == "disease":
                    efo_ids.append(hit["id"])
        
        self._efo_cache[cache_key] = efo_ids
        return efo_ids

    def get_associated_targets(self,efo_id: str, max_targets: int = 50) -> List[Dict[str, Any]]:
        query = """
            query AssociatedTargets($efoId: String!, $pageIndex: Int!, $pageSize: Int!) {
                disease(efoId: $efoId) {
                    associatedTargets(page: { index: $pageIndex, size: $pageSize }) {
                        count
                        rows {
                            score
                            target {
                                id
                                approvedSymbol
                            }
                        }
                    }
                }
            }
        """
        
        targets = []
        page_index = 0
        page_size = 50

        while len(targets) < max_targets:
            variables = {
                "efoId": efo_id,
                "pageIndex": page_index,
                "pageSize": page_size
            }
            
            data = query_open_targets(query, variables)
            rows = data["data"]["disease"]["associatedTargets"]["rows"]
            
            if not rows:
                break
            for row in rows:
                targets.append({
                    "target_id": row["target"]["id"],
                    "approved_symbol": row["target"]["approvedSymbol"],
                    "association_score": row["score"]
                })
            
            page_index += 1
            
            if len(rows) < page_size:
                break
        return targets[:max_targets]

    # ============================
    # Step 3: Target → Known Drugs
    # ============================

    @staticmethod
    def _parse_clinical_phase(stage: Any) -> int:
        if stage is None:
            return 0
        if isinstance(stage, (int, float)):
            return int(stage)
        s = str(stage).upper()
        if any(x in s for x in ["APPROVAL", "APPROVED", "WITHDRAWAL", "PHASE_4", "PHASE_IV", "PHASE 4"]):
            return 4
        if any(x in s for x in ["PHASE_3", "PHASE_III", "PHASE 3"]):
            return 3
        if any(x in s for x in ["PHASE_2", "PHASE_II", "PHASE 2"]):
            return 2
        if any(x in s for x in ["PHASE_1", "PHASE_I", "PHASE 1"]):
            return 1
        return 0

    def get_known_drugs_for_target(self, target_id: str, max_drugs: int = 50) -> List[Dict[str, Any]]:
        query = """
            query DrugCandidates($targetId: String!) {
                target(ensemblId: $targetId) {
                    drugAndClinicalCandidates {
                        count
                        rows {
                            drug {
                                id
                                name
                                drugType
                                molblock
                                maximumClinicalStage
                            }
                            maxClinicalStage
                        }
                    }
                }
            }
        """

        drugs = []
        try:
            data = query_open_targets(query, {"targetId": target_id})
            target_data = data.get("data", {}).get("target") if data.get("data") else None
            if not target_data:
                return []

            candidates = target_data.get("drugAndClinicalCandidates") or {}
            rows = candidates.get("rows", [])

            for row in rows:
                drug_obj = row.get("drug") or {}
                drug_id = drug_obj.get("id")
                if not drug_id:
                    continue
                pref_name = drug_obj.get("name")
                drug_type = drug_obj.get("drugType")
                molblock = drug_obj.get("molblock")
                raw_stage = drug_obj.get("maximumClinicalStage") or row.get("maxClinicalStage")
                phase = self._parse_clinical_phase(raw_stage)
                drugs.append({
                    "drug_id": drug_id,
                    "pref_name": pref_name,
                    "phase": phase,
                    "drug_type": drug_type,
                    "molblock": molblock,
                })
                if len(drugs) >= max_drugs:
                    break
        except Exception as e:
            logger.warning("Error fetching drugs for target %s: %s", target_id, e)
            return []

        return drugs[:max_drugs]

    # ============================
    # Step 4: Drug → IC50 Data (ChEMBL)
    # ============================

    def get_ic50_data_for_molecule(self, molecule_chembl_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        params = {
            "molecule_chembl_id": molecule_chembl_id,
            "standard_type__exact": "IC50",
            "limit": limit,
            "offset": 0
        }
        
        data = query_chembl("activity", params)

        ic50_records = []
        
        for activity in data.get("activities", []):
            if activity.get("standard_value") is None:
                continue
            
            ic50_records.append({
                "molecule_chembl_id": molecule_chembl_id,
                "standard_value": activity["standard_value"],
                "standard_units": activity.get("standard_units", "nM"),
                "target_chembl_id": activity.get("target_chembl_id"),
                "target_pref_name": activity.get("target_pref_name"),
                "assay_chembl_id": activity.get("assay_chembl_id"),
                "pchembl_value": activity.get("pchembl_value"),
                "document_chembl_id": activity.get("document_chembl_id")
            })
        
        return ic50_records

    # ============================
    # Step 5: Drug → Molecular Features (ChEMBL + OpenTargets molblock fallback)
    # ============================

    def get_molecule_properties(self, molecule_chembl_id: str, molblock: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cached = self._props_cache.get(molecule_chembl_id)
        if cached is not None and cached.get("smiles"):
            return cached

        data = None
        try:
            data = query_chembl(f"molecule/{molecule_chembl_id}")
        except Exception as e:
            logger.warning("Error fetching molecule %s from ChEMBL: %s", molecule_chembl_id, e)

        props = (data or {}).get("molecule_properties") or {}
        structs = (data or {}).get("molecule_structures") or {}
        canonical_smiles = structs.get("canonical_smiles")

        # If ChEMBL gave no SMILES or failed, try extracting SMILES and properties locally from OpenTargets molblock
        if not canonical_smiles and molblock:
            try:
                from rdkit import Chem
                from rdkit.Chem import Descriptors, Crippen, QED
                mol = Chem.MolFromMolBlock(molblock)
                if mol:
                    canonical_smiles = Chem.MolToSmiles(mol)
                    mw = Descriptors.MolWt(mol)
                    logp = Crippen.MolLogP(mol)
                    hbd = Descriptors.NumHDonors(mol)
                    hba = Descriptors.NumHAcceptors(mol)
                    rot_bonds = Descriptors.NumRotatableBonds(mol)
                    qed_score = round(QED.qed(mol), 3)
                    ro5 = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
                    result = {
                        "chembl_id": molecule_chembl_id,
                        "max_phase": None,
                        "molecular_formula": Descriptors.rdMolDescriptors.CalcMolFormula(mol),
                        "molecular_weight": mw,
                        "alogp": logp,
                        "aromatic_rings": Descriptors.NumAromaticRings(mol),
                        "mw_freebase": mw,
                        "hba": hba,
                        "hbd": hbd,
                        "heavy_atoms": mol.GetNumHeavyAtoms(),
                        "np_likeness_score": None,
                        "num_ro5_violations": ro5,
                        "psa": Descriptors.TPSA(mol),
                        "qed_weighted": qed_score,
                        "ro3_pass": None,
                        "rtb": rot_bonds,
                        "smiles": canonical_smiles,
                        "inchi": None,
                        "inchi_key": None,
                        "molfile_preview": molblock,
                    }
                    self._props_cache[molecule_chembl_id] = result
                    return result
            except Exception as e:
                logger.warning("Local molblock fallback parsing failed for %s: %s", molecule_chembl_id, e)

        if not data and not canonical_smiles:
            # Notice: Do NOT cache failure in self._props_cache to allow subsequent retries
            return None

        result = {
            "chembl_id": (data or {}).get("molecule_chembl_id", molecule_chembl_id),
            "max_phase": (data or {}).get("max_phase"),
            "molecular_formula": props.get("full_molformula"),
            "molecular_weight": props.get("full_mwt"),
            "alogp": props.get("alogp"),
            "aromatic_rings": props.get("aromatic_rings"),
            "mw_freebase": props.get("mw_freebase"),
            "hba": props.get("hba"),
            "hbd": props.get("hbd"),
            "heavy_atoms": props.get("heavy_atoms"),
            "np_likeness_score": props.get("np_likeness_score"),
            "num_ro5_violations": props.get("num_ro5_violations"),
            "psa": props.get("psa"),
            "qed_weighted": props.get("qed_weighted"),
            "ro3_pass": props.get("ro3_pass"),
            "rtb": props.get("rtb"),
            "smiles": canonical_smiles,
            "inchi": structs.get("standard_inchi"),
            "inchi_key": structs.get("standard_inchi_key"),
            "molfile_preview": structs.get("molfile", "") if structs.get("molfile") else (molblock or None)
        }
        if result.get("smiles"):
            self._props_cache[molecule_chembl_id] = result
        return result