import json
import logging
import math
import os
import re

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class AzureOpenAIChatClient:
    def __init__(self, 
                 api_key: str = None,
                 model_name: str = None,
                 base_url: str = None):
        # Resolve API key with Gemini priority, followed by Groq and OpenAI
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

        # Determine base URL
        if base_url:
            self.base_url = base_url
        elif os.environ.get("GEMINI_BASE_URL"):
            self.base_url = os.environ.get("GEMINI_BASE_URL")
        elif os.environ.get("GEMINI_API_KEY"):
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        elif os.environ.get("GROQ_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
            self.base_url = "https://api.groq.com/openai/v1"
        else:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        # Determine model name
        if model_name:
            self.deployment_name = model_name
        elif "generativelanguage.googleapis.com" in self.base_url:
            self.deployment_name = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        elif "groq.com" in self.base_url:
            self.deployment_name = os.environ.get("GROQ_MODEL", "llama3-8b-8192")
        else:
            self.deployment_name = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

        self.has_key = bool(self.api_key and self.api_key.strip() not in ("", "dummy", "none", "dummy_offline_key"))

        if self.has_key:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                max_retries=1,
                timeout=float(os.environ.get("GEMINI_TIMEOUT", "25.0"))
            )
        else:
            self.client = None

    def generate_disease_name_from_prompt(self, user_text: str) -> str:
        system_prompt = {
            "role": "system",
            "content": """
You are a Disease Name Resolver for biomedical APIs.

Your task:
- You will receive user input that may contain:
  - Symptoms
  - One disease name
  - Multiple disease names
  - Or a combination of symptoms and disease names
- Based on the input, identify the most accurate and standardized disease name(s)
  that are compatible with api.platform.opentargets.org (EFO-compatible).

Rules you MUST follow:
1. Always return disease names that resolve correctly on api.platform.opentargets.org.
2. Use standardized clinical disease names aligned with EFO / Open Targets ontology.
3. Infer diseases from symptoms only when explicit disease names are not provided.
4. Return multiple diseases only when the input clearly indicates more than one condition.
5. Do NOT include explanations, reasoning, comments, or extra text.
6. Output MUST be valid JSON only.
7. The JSON key must be exactly "disease".
8. The value must be an array of one or more disease name strings.
9. Do NOT include duplicates, abbreviations, or non-disease terms.
10. Use lowercase disease names unless capitalization is required by convention.

Strict output format:
{"disease":["<disease name 1>","<disease name 2>"]}

VALID EXAMPLES (ONLY RETURN THE JSON, NO EXTRA TEXT):

{"disease":["breast cancer"]}

{"disease":["prostate cancer"]}

{"disease":["lung cancer"]}

{"disease":["colorectal cancer"]}

{"disease":["type 2 diabetes mellitus"]}

{"disease":["hypertension"]}

{"disease":["alzheimer disease"]}

{"disease":["coronary artery disease"]}

{"disease":["chronic obstructive pulmonary disease"]}

{"disease":["asthma"]}

{"disease":["rheumatoid arthritis"]}

{"disease":["parkinson disease"]}

{"disease":["multiple sclerosis"]}

{"disease":["chronic kidney disease"]}

{"disease":["breast cancer","lung cancer"]}

{"disease":["type 2 diabetes mellitus","hypertension"]}

If the input is ambiguous, return the most likely disease name(s)
that follow Open Targets Platform naming conventions.

"""
        }
        chat_prompt = [
            system_prompt,
            {
                "role": "user",
                "content": user_text
            }
        ]

        if not self.has_key or not self.client:
            return self._fallback_disease_resolver(user_text)

        try:
            completion = self.client.chat.completions.create(
                max_tokens=2000,  
                temperature=0.1,  
                top_p=0.21,
                model=self.deployment_name,
                messages=chat_prompt
            )

            content = completion.choices[0].message.content or "{}"
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            return content
        except Exception as e:
            if self.deployment_name != "gemini-flash-lite-latest" and "generativelanguage.googleapis.com" in self.base_url:
                try:
                    completion = self.client.chat.completions.create(
                        max_tokens=2000,
                        temperature=0.1,
                        top_p=0.21,
                        model="gemini-flash-lite-latest",
                        messages=chat_prompt
                    )
                    content = completion.choices[0].message.content or "{}"
                    content = content.strip()
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\s*", "", content)
                        content = re.sub(r"\s*```$", "", content)
                    return content
                except Exception:
                    pass
            logger.warning("LLM disease name generation failed or quota exceeded (%s). Using fallback resolver.", e)
            return self._fallback_disease_resolver(user_text)

    def _fallback_disease_resolver(self, user_text: str) -> str:
        """Deterministic biomedical query resolver for offline/fallback mode."""
        cleaned = user_text.strip()
        # Extract content from (query(...)) or query(...) wrapper
        m = re.search(r"query\s*\(\s*(.*?)\s*\)", cleaned, re.IGNORECASE)
        if m:
            cleaned = m.group(1).strip()

        cleaned = re.sub(
            r"(?i)\b(i have|i suffer from|symptoms of|treatment for|cure for|patient with|suffering from|diagnosed with|please find drugs for)\b",
            "",
            cleaned,
        )
        cleaned = re.sub(r"[^\w\s-]", "", cleaned).strip().lower()

        # Symptom to standardized EFO disease mappings
        symptom_map = {
            "chest pain": "angina pectoris",
            "high blood pressure": "hypertension",
            "high sugar": "diabetes mellitus",
            "joint pain": "osteoarthritis",
            "shortness of breath": "dyspnea",
        }
        if cleaned in symptom_map:
            cleaned = symptom_map[cleaned]

        if not cleaned:
            cleaned = user_text.strip().lower()
        return json.dumps({"disease": [cleaned]})

    def generate_report_from_smiles_ic50_value_association_score_target_symbol_max_phase(
            self,
            smiles: str,
            ic50_value: float,
            association_score: float,
            target_symbol: str,
            max_phase: int,
            user_prompt: str = ""
    ) -> str:
        """
        Generate a comprehensive report for a compound given its SMILES and metrics.

        Parameters
        - smiles: SMILES string of the compound
        - ic50_value: IC50 measurement (assumed nanomolar (nM) unless specified)
        - association_score: association score (assumed normalized between 0 and 1)
        - target_symbol: gene/protein target symbol (e.g., EGFR)
        - max_phase: highest clinical phase reached (0: preclinical, 1-4: clinical phases)
        - user_prompt: optional extra instructions for the report

        Returns a human-readable report generated by the chat model.
        """

        # Try to compute RDKit descriptors when RDKit is available. Fail gracefully if not.
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, rdMolDescriptors, Crippen
            rdkit_available = True
        except Exception:
            rdkit_available = False

        # Derived metrics from IC50 (assuming ic50_value is in nM)
        pIC50 = None
        potency = "unknown"
        try:
            if ic50_value is not None and ic50_value > 0:
                # pIC50 where IC50 is in nM: pIC50 = -log10(IC50 [M]) = 9 - log10(IC50 [nM])
                pIC50 = 9.0 - math.log10(float(ic50_value))
                pIC50 = round(pIC50, 3)
                ic50 = float(ic50_value)
                if ic50 <= 10:
                    potency = "very high potency (<10 nM)"
                elif ic50 <= 100:
                    potency = "high potency (10-100 nM)"
                elif ic50 <= 1000:
                    potency = "moderate potency (100-1000 nM)"
                elif ic50 <= 10000:
                    potency = "low potency (1-10 µM)"
                else:
                    potency = "very low potency / inactive (>10 µM)"
        except Exception:
            pass

        # Interpret association score (assumed 0-1 if within range)
        assoc_interp = "unknown"
        try:
            if association_score is None:
                assoc_interp = "unknown association"
            else:
                assoc = float(association_score)
                if 0 <= assoc <= 1:
                    if assoc >= 0.8:
                        assoc_interp = "strong association"
                    elif assoc >= 0.5:
                        assoc_interp = "moderate association"
                    elif assoc >= 0.2:
                        assoc_interp = "weak association"
                    else:
                        assoc_interp = "negligible association"
                else:
                    assoc_interp = "association score out of expected 0-1 range; interpret cautiously"
        except Exception:
            pass

        rdkit_data = {}
        if rdkit_available:
            try:
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:
                    mw = Descriptors.MolWt(mol)
                    logp = Crippen.MolLogP(mol)
                    hbd = rdMolDescriptors.CalcNumHBD(mol)
                    hba = rdMolDescriptors.CalcNumHBA(mol)
                    tpsa = rdMolDescriptors.CalcTPSA(mol)
                    rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
                    heavy_atoms = mol.GetNumHeavyAtoms()
                    formula = rdMolDescriptors.CalcMolFormula(mol)
                    violations = []
                    if mw > 500:
                        violations.append("MW>500")
                    if logp > 5:
                        violations.append("logP>5")
                    if hbd > 5:
                        violations.append("HBD>5")
                    if hba > 10:
                        violations.append("HBA>10")

                    from rdkit.Chem import QED
                    from pindora import _PAINS_CATALOG

                    qed_score = round(QED.qed(mol), 3)
                    bertz = Descriptors.BertzCT(mol)
                    sascore = round(min(10.0, max(1.0, (bertz / 150.0) + 1.0)), 1)
                    pains_alert = _PAINS_CATALOG.HasMatch(mol)

                    # Compute Druggability MPO score (0-100)
                    s_pot = max(0.0, min(1.0, 1.0 - math.log10(max(float(ic50_value), 0.001)) / 4.0)) if ic50_value else 0.5
                    s_asc = max(0.0, min(1.0, float(association_score))) if association_score else 0.5
                    s_syn = max(0.0, min(1.0, 1.0 - (sascore - 1.0) / 9.0))
                    s_pen = 0.25 * len(violations) + (0.50 if pains_alert else 0.0)
                    raw_dscore = 0.35 * s_pot + 0.25 * s_asc + 0.25 * qed_score + 0.15 * s_syn - 0.10 * s_pen
                    druggability_score = int(round(max(0.0, min(1.0, raw_dscore)) * 100))

                    rdkit_data = {
                        "molecular_weight": round(mw, 2),
                        "formula": formula,
                        "logP": round(logp, 2),
                        "hbd": int(hbd),
                        "hba": int(hba),
                        "tpsa": round(tpsa, 2),
                        "rotatable_bonds": int(rot_bonds),
                        "heavy_atom_count": int(heavy_atoms),
                        "qed": qed_score,
                        "sascore": sascore,
                        "pains_alert": pains_alert,
                        "druggability_score": druggability_score,
                        "lipinski_violations_count": len(violations),
                        "lipinski_violations": violations
                    }
                else:
                    rdkit_data = {"error": "invalid SMILES or RDKit could not parse SMILES"}
            except Exception as e:
                rdkit_data = {"error": f"RDKit failed to compute descriptors: {e}"}

        # Ligand efficiency (simple approximation LE = pIC50 / heavy_atom_count)
        ligand_efficiency = None
        try:
            if pIC50 is not None and rdkit_data.get("heavy_atom_count"):
                ha = rdkit_data["heavy_atom_count"]
                if ha > 0:
                    ligand_efficiency = round(pIC50 / ha, 3)
        except Exception:
            pass

        # Prepare payload for the LLM with both raw and derived values
        payload = {
            "user_prompt": user_prompt or "",
            "smiles": smiles,
            "ic50_nM": ic50_value,
            "pIC50": pIC50,
            "potency": potency,
            "association_score": association_score,
            "association_interpretation": assoc_interp,
            "target_symbol": target_symbol,
            "max_phase": max_phase,
            "ligand_efficiency": ligand_efficiency,
            "rdkit": rdkit_data,
            "assumptions": [
                "IC50 values are assumed to be in nanomolar (nM) unless specified.",
                "Association score is assumed to be normalized between 0 and 1 unless specified.",
                "Derived descriptors may be omitted if RDKit is unavailable or SMILES is invalid."
            ]
        }

        # System prompt guiding how the report should be written
        system_prompt = {
            "role": "system",
            "content": (
                "You are an expert medicinal chemist and drug discovery scientist. "
                "Given the compound data (SMILES, IC50, association score, target symbol, clinical phase) and any derived metrics, "
                "generate a comprehensive, evidence-based report suitable for a cross-functional team (med chem, bio, DMPK, clinical). "
                "The report must include the following sections:\n\n"
                "1) Executive summary (2-3 lines): one-sentence conclusion about the compound's promise and primary risk.\n"
                "2) Compound summary: key identifiers and computed descriptors (molecular weight, formula, logP, HBD/HBA, TPSA, heavy atoms, rotatable bonds), mention if unavailable.\n"
                "3) Bioactivity and potency: interpret IC50 (in nM), pIC50, potency category, ligand efficiency, and what these imply for target engagement and in vitro vs in vivo expectations.\n"
                "4) Target & disease context: interpret association score and target symbol to suggest likely therapeutic areas and whether the target is a plausible disease-modifying mechanism.\n"
                "5) Clinical development perspective: explain the implication of the reported 'max_phase' (0: preclinical, 1-4: clinical phases) and recommend next milestones to advance.\n"
                "6) ADME/Tox and developability flags: highlight Lipinski violations or concerning physicochemical properties and their likely consequences.\n"
                "7) Recommended next steps: prioritized experiments (potency confirmation, selectivity, target engagement, ADME/Tox assays, in vivo models) and go/no-go criteria.\n"
                "8) Assumptions and confidence: explicitly list assumptions you used (including about units) and the confidence level for each recommendation.\n\n"
                "Be explicit about limitations and do NOT invent experimental measurements. Use the provided derived metrics directly. Present key numbers in a short bullet list or simple table at the top of the report. Keep the language professional, clear, and concise."
            )
        }

        chat_prompt = [
            system_prompt,
            {"role": "user", "content": json.dumps(payload, indent=2)}
        ]

        if not self.has_key or not self.client:
            return self._generate_fallback_report(payload)

        try:
            completion = self.client.chat.completions.create(
                max_tokens=3000,
                temperature=0.2,
                top_p=0.9,
                model=self.deployment_name,
                messages=chat_prompt
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            if self.deployment_name != "gemini-flash-lite-latest" and "generativelanguage.googleapis.com" in self.base_url:
                try:
                    completion = self.client.chat.completions.create(
                        max_tokens=3000,
                        temperature=0.2,
                        top_p=0.9,
                        model="gemini-flash-lite-latest",
                        messages=chat_prompt
                    )
                    return completion.choices[0].message.content or ""
                except Exception:
                    pass
            logger.warning("LLM report generation failed (%s). Using fallback report generator.", e)
            return self._generate_fallback_report(payload)

    def _generate_fallback_report(self, payload: dict) -> str:
        """Deterministic scientific report used when LLM quota is exhausted or unavailable."""
        rd = payload.get("rdkit", {})
        violations = rd.get("lipinski_violations", [])
        viol_str = ", ".join(violations) if violations else "None (Passes Lipinski's Rule of 5)"

        phase_map = {
            0: "Preclinical / Research Discovery",
            1: "Phase 1 Clinical Trials (Safety & Tolerance)",
            2: "Phase 2 Clinical Trials (Proof of Concept & Efficacy)",
            3: "Phase 3 Clinical Trials (Comparative Confirmatory)",
            4: "Phase 4 / Approved Drug (Post-Market Surveillance)"
        }
        phase_desc = phase_map.get(payload.get("max_phase", 0), "Preclinical")

        ic50_val = payload.get("ic50_nM")
        ic50_str = f"{float(ic50_val):.2f}" if ic50_val is not None else "N/A"
        assoc_val = payload.get("association_score")
        assoc_str = f"{float(assoc_val):.3f}" if assoc_val is not None else "N/A"

        dscore = rd.get("druggability_score", 50)
        qed = rd.get("qed", "N/A")
        sascore = rd.get("sascore", "N/A")
        pains = rd.get("pains_alert", False)
        pains_str = "⚠ Structural Alert (PAINS Match)" if pains else "✓ Clean (No PAINS Match)"
        pains_status = "Flagged" if pains else "Clean"

        dscore_status = "High Potential" if (isinstance(dscore, (int, float)) and dscore >= 70) else "Moderate" if (isinstance(dscore, (int, float)) and dscore >= 45) else "Optimization Required"
        qed_status = "Optimal" if (isinstance(qed, (int, float)) and qed >= 0.67) else "Acceptable" if (isinstance(qed, (int, float)) and qed >= 0.50) else "Low"
        sas_status = "Accessible" if (isinstance(sascore, (int, float)) and sascore <= 4.0) else "Moderate" if (isinstance(sascore, (int, float)) and sascore <= 6.0) else "Complex"

        target_sym = payload.get('target_symbol', 'N/A')
        potency_class = payload.get('potency', 'unknown')

        report = rf"""# Medicinal Chemistry & Compound Assessment Dossier

## 1. Executive Summary & Clinical Assessment
The compound candidate evaluated for biological target **{target_sym}** demonstrates **{potency_class}** with a predicted IC50 of **{ic50_str} nM** (pIC50: {payload.get('pIC50', 'N/A')}). 
Overall composite druggability assessment yields an MPO score of **{dscore}/100** ({dscore_status}) with {len(violations)} Lipinski violation(s) and a **{pains_str}** chemical safety profile.

## 2. Multi-Parameter Optimization (MPO) Scorecard

| Discovery Parameter | Value | Reference Standard | Assessment |
| :--- | :--- | :--- | :--- |
| **Composite Druggability Score** | **{dscore} / 100** | $\ge 70$: Favorable | {dscore_status} |
| **QED (Drug-Likeness)** | **{qed}** | $\ge 0.67$: High oral drug likeness | {qed_status} |
| **Synthetic Feasibility (SAScore)** | **{sascore} / 10** | $\le 4.0$: Readily synthesizable | {sas_status} |
| **PAINS Filter Screening** | **{pains_str}** | Zero assay interference alerts | {pains_status} |
| **Lipinski Rule of 5** | **{len(violations)} Violation(s)** | $\le 1$ violation permissible | {viol_str} |
| **Ligand Efficiency (LE)** | **{payload.get('ligand_efficiency', 'N/A')}** | $\ge 0.30$ kcal/mol/HA | Potency per heavy atom |

## 3. Physicochemical & Structural Descriptors
* **Canonical SMILES**: `{payload.get('smiles', 'N/A')}`
* **Molecular Formula**: `{rd.get('formula', 'N/A')}`
* **Molecular Weight**: `{rd.get('molecular_weight', 'N/A')} g/mol` (Lipinski criterion: $\le 500$)
* **Calculated LogP**: `{rd.get('logP', 'N/A')}` (Optimal lipophilicity: $1.0 - 4.5$)
* **Hydrogen Bond Donors (HBD)**: `{rd.get('hbd', 'N/A')}` (Lipinski criterion: $\le 5$)
* **Hydrogen Bond Acceptors (HBA)**: `{rd.get('hba', 'N/A')}` (Lipinski criterion: $\le 10$)
* **Topological Polar Surface Area (TPSA)**: `{rd.get('tpsa', 'N/A')} Å²` (Optimal gut-blood permeation $< 140$ Å²)
* **Rotatable Bonds**: `{rd.get('rotatable_bonds', 'N/A')}` (Flexibility criterion $\le 10$)
* **Heavy Atom Count**: `{rd.get('heavy_atom_count', 'N/A')}`

## 4. Bioactivity & Potency Profile
* **Predicted IC50**: **{ic50_str} nM**
* **pIC50 (-log IC50 [M])**: **{payload.get('pIC50', 'N/A')}**
* **Potency Classification**: **{potency_class}**
* **Ligand Efficiency (LE)**: **{payload.get('ligand_efficiency', 'N/A')}**

## 5. Target & Disease Mechanism Context
* **Validated Biological Target**: **{target_sym}**
* **Genetic Association Score**: **{assoc_str}** ({payload.get('association_interpretation', 'N/A')})
* **Clinical Benchmark Stage**: **{phase_desc}** (Phase {payload.get('max_phase', 0)})

## 6. ADME / Pharmacokinetics & Safety Flags
* **Rule of 5 Compliance**: {viol_str}
* **Developability Assessment**: {"Compound displays optimal drug-like properties meeting oral bioavailability criteria." if not violations else f"Compound exhibits {len(violations)} rule flags ({viol_str}). Consider scaffold tuning to reduce molecular weight or lipophilicity."}
* **Assay Interference Warning**: {"No known pan-assay interference motifs detected. Suitable for biochemical screening." if not pains else "Contains potential reactive or promiscuous functional groups. Secondary orthogonal assay recommended."}

## 7. Recommended Preclinical Next Steps
1. **Binding Affinity Confirmation**: Validate equilibrium dissociation constant ($K_d$) or $IC_{50}$ via Surface Plasmon Resonance (SPR) or Radioligand binding against `{target_sym}`.
2. **Cellular Efficacy & Selectivity**: Measure on-target antiproliferative or functional pathway modulation in human disease cell lines.
3. **Hepatic Microsomal Stability**: Quantify intrinsic clearance ($Cl_{int}$) across human (HLM) and mouse (MLM) liver microsomes.
4. **Permeability & Efflux Profiling**: Screen in Caco-2 or MDCK-MDR1 bidirectional transport assays to assess P-gp liability.
"""
        return report.strip()
