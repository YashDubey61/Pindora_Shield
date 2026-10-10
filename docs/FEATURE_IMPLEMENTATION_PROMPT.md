# PINDORA SHIELD: HIGH-SPEED FEATURE SPECIFICATION & AGENT IMPLEMENTATION PROMPT

> **Instruction for the Implementing AI Agent:**  
> You are tasked with implementing the next-generation feature suite for **Pindora Shield**, an AI-driven drug discovery and de novo molecular generation platform.  
> ⚡ **CRITICAL PERFORMANCE PRINCIPLE (ZERO-LATENCY GENERATION):**  
> Under NO circumstances should any feature add heavy computational overhead or latency to the primary molecular generation pipeline.  
> 1. The core generation pipeline (`/api/drug_discovery`) must return in **seconds**, utilizing only microsecond-level vectorized calculations (RDKit descriptors & pre-warmed MatriX models).  
> 2. All computationally heavy operations (3D UFF force-field optimization, LLM research report synthesis, MCS graph search, multi-file SDF packaging) MUST be strictly **on-demand (lazy-loaded)** upon explicit user interaction.

---

## 📌 Table of Contents
1. [Latency Elimination Guidelines (Zero Pipeline Overhead)](#1-latency-elimination-guidelines-zero-pipeline-overhead)
2. [Feature 1: Ultra-Fast Instant Drug-Likeness & Safety (QED, Heuristic SAS, PAINS)](#feature-1-ultra-fast-instant-drug-likeness--safety-qed-heuristic-sas-pains)
3. [Feature 2: On-Demand Interactive 3D Conformer Viewer (Lazy 3Dmol.js)](#feature-2-on-demand-interactive-3d-conformer-viewer-lazy-3dmoljs)
4. [Feature 3: Instant Composite Druggability Score & Pareto Ranking (Zero Backend Overhead)](#feature-3-instant-composite-druggability-score--pareto-ranking-zero-backend-overhead)
5. [Feature 4: High-Speed Scaffold Alignment (Replacing Heavy MCS with Murcko Scaffolds)](#feature-4-high-speed-scaffold-alignment-replacing-heavy-mcs-with-murcko-scaffolds)
6. [Feature 5: Client-Side Export Engine (Instant CSV & On-Demand PDF Dossier)](#feature-5-client-side-export-engine-instant-csv--on-demand-pdf-dossier)
7. [Feature 6: Lightweight SSE Live Progress Stepper](#feature-6-lightweight-sse-live-progress-stepper)
8. [Acceptance Criteria & Verification Checklist](#acceptance-criteria--verification-checklist)

---

## 1. Latency Elimination Guidelines (Zero Pipeline Overhead)

The agent must strictly adhere to the following rules to prevent generation slowdowns:

| Heavy Bottleneck (ELIMINATED / MOVED) | Latency Added | Fast Solution |
| :--- | :---: | :--- |
| **Full MCS Graph Isomorphism (`rdFMCS`)** | ❌ 3 – 15s per pair | ✅ **Eliminated from pipeline.** Replaced with instant Bemis-Murcko scaffold matching (< 2ms). |
| **Generating 3D Coordinates & UFF Optimization for all molecules during generation** | ❌ 10 – 30s total | ✅ **Moved to strictly On-Demand.** Only generate 3D coordinates when user clicks "View 3D" on a specific card. |
| **Synchronous LLM Report Generation in pipeline loop** | ❌ 5 – 10s per drug | ✅ **Moved to strictly On-Demand.** LLM is only called when user clicks "Generate Clinical Report". |
| **Loading large SAScore fragment dictionaries from disk repeatedly** | ❌ 1 – 3s | ✅ **In-memory pre-warmed singletons** or native RDKit Bertz Complexity / QED calculation (< 1ms). |
| **Sequential Uncached ChEMBL / OpenTargets queries** | ❌ 4 – 8s | ✅ **Strict limits & In-memory LRU caching** (`max_targets=3`, `max_candidates=3`). |

---

## Feature 1: Ultra-Fast Instant Drug-Likeness & Safety (QED, Heuristic SAS, PAINS)

### Objective
Enrich molecules with critical drug-likeness descriptors without adding any noticeable delay to generation (< 5ms per molecule).

### 1.1 Backend Implementation Details
* **File to Modify:** `pindora.py` (inside `get_molecular_properties(smiles)`)
* **Requirements:**
  1. **QED (Quantitative Estimate of Drug-likeness):**
     * Use native RDKit C++ implementation: `Chem.QED.qed(mol)` (runs in < 0.2ms).
  2. **Bemis-Murcko Complexity / Heuristic Synthesizability:**
     * Rather than disk-heavy fragment databases, compute synthetic feasibility instantly using RDKit topological indices:
       ```python
       from rdkit.Chem import Descriptors
       # BertzCT complexity normalized to 1-10 synthetic accessibility scale
       bertz = Descriptors.BertzCT(mol)
       # Approximate SAScore (1.0 = easy, 10.0 = hard) in <0.1ms
       sascore = round(min(10.0, max(1.0, (bertz / 150.0) + 1.0)), 1)
       ```
  3. **Instant PAINS Screening:**
     * Instantiate `FilterCatalog` **once** at module startup (singleton), NOT inside the per-molecule loop:
       ```python
       # At module level (loaded once at startup)
       from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
       _PARAMS = FilterCatalogParams()
       _PARAMS.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
       _PAINS_CATALOG = FilterCatalog(_PARAMS)
       ```
     * In `get_molecular_properties()`: `pains_alert = _PAINS_CATALOG.HasMatch(mol)` (< 0.5ms).
  4. **Lipinski Rule of 5 Count:**
     * Calculate 0 to 4 violations count using existing RDKit descriptors (`MW, LogP, HBD, HBA`).
* **Output Schema:**
  ```json
  "properties": {
    "molecular_weight": 342.12,
    "logp": 2.45,
    "hbd": 2,
    "hba": 4,
    "rotatable_bonds": 3,
    "aromatic_rings": 2,
    "qed": 0.82,
    "sascore": 2.7,
    "lipinski_violations": 0,
    "pains_alert": false
  }
  ```

### 1.2 Frontend Implementation Details
* **File to Modify:** `frontend/src/pages/ResultPage.tsx`
* **UI Badges:**
  * Render compact status badges on each molecule card:
    * `QED: 0.82` (Green $\ge 0.67$, Amber $0.50-0.66$, Red $< 0.50$)
    * `Synth: Easy (2.7)` (Green $\le 4.0$, Amber $4.1-6.0$, Red $> 6.0$)
    * `PAINS: Clean` (Green badge) or `PAINS Alert` (Warning badge)
    * `Ro5: 0 Violations`

---

## Feature 2: On-Demand Interactive 3D Conformer Viewer (Lazy 3Dmol.js)

### Objective
Provide a 3D molecular viewer with zero upfront generation delay. 3D coordinates are calculated **only when the user requests to see them**.

### 2.1 Backend Implementation Details
* **Files to Modify:** `routes/drugs.py`, `utils/generate_3d.py`
* **Workflow:**
  1. During the initial discovery run, **do NOT generate 3D models**.
  2. When the user clicks the "3D View" button on a molecule card, the frontend triggers:
     `POST /api/generate-3d` with `{ "input_smile": smiles }`.
  3. `utils/generate_3d.py` performs 3D embedding (`AllChem.EmbedMolecule` + `AllChem.UFFOptimizeMolecule`) and immediately returns:
     ```json
     {
       "status": "success",
       "smiles": "...",
       "sdf_block": "...", 
       "num_atoms": 24,
       "num_bonds": 26
     }
     ```

### 2.2 Frontend Implementation Details
* **File to Modify:** `frontend/src/pages/MoleculeViewer.tsx` (or integrated modal inside `ResultPage.tsx`)
* **Viewer Engine:** Use `3Dmol.js` embedded canvas.
  ```typescript
  // Load 3D conformer dynamically from the returned sdf_block
  viewer.addModel(data.sdf_block, "sdf");
  viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } });
  viewer.zoomTo();
  viewer.render();
  ```
* **Styles & Interaction:**
  * Toggle between: `Ball & Stick`, `Stick`, `Space-filling (CPK spheres)`.
  * Controls: Orbit, zoom, auto-rotation toggle, reset view.

---

## Feature 3: Instant Composite Druggability Score & Pareto Ranking (Zero Backend Overhead)

### Objective
Rank molecules using a multi-parameter optimization (MPO) composite score computed **instantly in the client/backend** with arithmetic only.

### 3.1 Arithmetic Scoring Formula ($O(1)$ computation)
$$\text{Score} = \text{clamp}\left(100 \times \left(0.35 \cdot S_{\text{potency}} + 0.25 \cdot S_{\text{assoc}} + 0.25 \cdot \text{QED} + 0.15 \cdot S_{\text{synth}} - 0.10 \cdot S_{\text{penalty}}\right), 0, 100\right)$$

* $S_{\text{potency}} = \text{clamp}(1.0 - \frac{\log_{10}(\text{IC50})}{4.0}, 0.0, 1.0)$
* $S_{\text{assoc}} = \text{clamp}(\text{Association\_Score}, 0.0, 1.0)$
* $S_{\text{synth}} = \text{clamp}(1.0 - \frac{\text{SAScore} - 1.0}{9.0}, 0.0, 1.0)$
* $S_{\text{penalty}} = 0.25 \times \text{Lipinski\_Violations} + (0.50 \text{ if pains\_alert else } 0.0)$

### 3.2 Frontend Implementation Details
* **File to Modify:** `frontend/src/pages/ResultPage.tsx`
* **Features:**
  * **Sort Bar:**
    * "Highest Druggability Score" (Default)
    * "Highest Potency (Lowest IC50)"
    * "Best Synthesizability"
    * "Highest Similarity to Lead Drug"
  * **Quick Filter Toggles:**
    * "Hide PAINS alerts"
    * "Lipinski Compliant only"
    * "QED $\ge 0.60$"
  * **Score Pill:** Display a vibrant score badge (`88/100`) on each candidate card.

---

## Feature 4: High-Speed Scaffold Alignment (Replacing Heavy MCS with Murcko Scaffolds)

### Objective
Show structural differences between the seed drug and the generated molecule without the catastrophic latency of NP-complete MCS algorithms.

### 4.1 Backend Implementation Details
* **File to Modify:** `routes/drugs.py`
* **New Route:** `POST /api/molecule/scaffold_info`
* **High-Speed Algorithm:**
  1. Use Bemis-Murcko scaffold extraction (`rdkit.Chem.Scaffolds.MurckoScaffold.GetScaffoldForMol`):
     ```python
     from rdkit.Chem.Scaffolds import MurckoScaffold
     # Extract core ring scaffold in <0.5ms (vs 10,000ms for rdFMCS)
     seed_scaffold = MurckoScaffold.MurckoScaffoldSmiles(seed_smiles)
     cand_scaffold = MurckoScaffold.MurckoScaffoldSmiles(candidate_smiles)
     scaffold_preserved = (seed_scaffold == cand_scaffold)
     ```
  2. Return:
     ```json
     {
       "seed_scaffold": seed_scaffold,
       "candidate_scaffold": cand_scaffold,
       "scaffold_preserved": scaffold_preserved
     }
     ```

### 4.2 Frontend Implementation Details
* Display a clean "Core Scaffold Preserved" or "Scaffold Hopping (Novel Ring System)" tag.

---

## Feature 5: Client-Side Export Engine (Instant CSV & On-Demand PDF Dossier)

### Objective
Enable fast data export without burdening the FastAPI backend.

### 5.1 Frontend Implementation Details
* **File to Modify:** `frontend/src/pages/ResultPage.tsx`
* **1. Instant CSV Export (100% Client-Side):**
  * Generate and trigger download of CSV directly in the browser via `Blob` URL in $< 50\text{ms}$:
  * Columns: `Disease, Target, Seed Drug, Candidate SMILES, Druggability Score, IC50 (nM), Association Score, Phase, MW, LogP, QED, SAScore, PAINS`.
* **2. On-Demand Candidate Dossier (PDF):**
  * Utilize the existing `Report.tsx` modal.
  * Add a "Print / Save PDF" button invoking browser `window.print()` with `@media print` styling, or `html2pdf.js` for instant, local vector PDF creation.

---

## Feature 6: Lightweight SSE Live Progress Stepper

### Objective
Provide immediate visual responsiveness during the 10-15s generation process with zero polling overhead.

### 6.1 Backend Implementation Details
* **File to Modify:** `routes/drugs.py`
* **Route:** `GET /api/drug_discovery_stream?text={prompt}` (StreamingResponse with `text/event-stream`)
* **Milestone Events:**
  1. `{"step": 1, "label": "Extracting target disease..."}`
  2. `{"step": 2, "label": "Querying biological targets..."}`
  3. `{"step": 3, "label": "Fetching known reference inhibitors..."}`
  4. `{"step": 4, "label": "TenGAN generating novel analogs..."}`
  5. `{"step": 5, "label": "Running MatriX bioactivity predictions..."}`
  6. `{"step": 6, "label": "Complete", "data": [...]}`

### 6.2 Frontend Implementation Details
* **File to Modify:** `frontend/src/pages/loading.tsx`
* Display active progress steps ticking off in real time so the user experiences zero perceived idle time.

---

## Acceptance Criteria & Verification Checklist

- [ ] **Zero Generation Slowdown:** Total `/api/drug_discovery` execution time is unaffected (or faster due to caching).
- [ ] **No MCS Blocking:** No `rdFMCS` calls in the generation path.
- [ ] **Lazy 3D:** 3D coordinates are strictly computed on-demand via `/api/generate-3d`.
- [ ] **Singleton PAINS Catalog:** `FilterCatalog` is initialized once at startup.
- [ ] **Instant Druggability Score:** Every molecule displays a calculated 0–100 score with zero API lag.
- [ ] **Client-Side CSV Export:** Users can download a CSV of all candidates in under 1 second.
- [ ] **Interactive 3D Viewer:** Opens seamlessly when requested with CPK coloring and style controls.
