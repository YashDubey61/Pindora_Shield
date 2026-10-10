"""
Pipeline: Disease → Target Protein → Molecules → IC50 (from ChEMBL)
Author: Modelix
Date: 2025-12-25

===================================================================================
COMPLETE PIPELINE FOR IC50 PREDICTION MODEL DATA COLLECTION
===================================================================================

This script queries the Open Targets Platform GraphQL API and ChEMBL REST API to:
1. Map a disease name to an EFO (Experimental Factor Ontology) identifier
2. Retrieve associated target proteins for that disease
3. For each target, fetch known drugs (molecules) that modulate it
4. For each drug, retrieve IC50 bioactivity data from the ChEMBL database
5. Extract molecular features (e.g., molecular weight, logP, HBA, HBD) from ChEMBL

The output is a pandas DataFrame containing the collected data, which can be used 
to build a machine-learning model for IC50 prediction.

===================================================================================
DEPENDENCIES
===================================================================================
Install with:
    pip install requests pandas

Required libraries:
- requests: For making HTTP requests to GraphQL and REST APIs
- pandas: For data manipulation and storage
- json: For parsing JSON responses (built-in)
- typing: For type hints (built-in)

===================================================================================
DATA SOURCES
===================================================================================
1. Open Targets Platform (GraphQL API): Provides disease-target associations, 
   known drugs, and mechanisms of action
2. ChEMBL (REST API): Provides bioactivity data (IC50), molecular properties, 
   and chemical structures

===================================================================================
USE CASES FOR MODEL BUILDING
===================================================================================
Q: Is it good to build a model to predict IC50 from a string (SMILES)?

A: YES! This is a well-established task in computational drug discovery:

PROS:
✓ Large datasets available: ChEMBL contains millions of IC50 measurements
✓ Validated approach: Many published models exist (DeepChem, Chemprop, etc.)
✓ Useful for drug discovery: Predicting potency saves time and resources
✓ Rich features: Can extract 200+ molecular descriptors from SMILES
✓ Multiple modeling approaches: Can use fingerprints, graphs, or transformers

CONS:
✗ Assay-dependent: IC50 values vary by assay conditions, target, cell line
✗ Data quality: Need to filter for standard units, valid structures
✗ Target-specific: Models often work best when trained per target
✗ Generalization: May not work well for novel chemical scaffolds

RECOMMENDED APPROACH:
1. Filter data: Use only IC50 values in standard units (nM)
2. Target-specific models: Train separate models per target protein
3. Feature engineering: Combine molecular descriptors + fingerprints
4. Use pIC50: Convert IC50 to -log10(IC50) for better distribution
5. Cross-validation: Use scaffold splitting to test on novel structures

===================================================================================
FEATURES AVAILABLE FROM ChEMBL (based on molecule input)
===================================================================================

INPUT OPTIONS:
- Molecule Name: "aspirin", "ibuprofen"
- SMILES: "CC(=O)Oc1ccccc1C(=O)O"
- ChEMBL ID: "CHEMBL25"
- InChI Key: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"

FEATURES YOU CAN EXTRACT:

1. MOLECULAR PROPERTIES (from molecule_properties):
   - full_mwt: Molecular weight including salt
   - alogp: Calculated logP (lipophilicity)
   - hba: Hydrogen bond acceptors
   - hbd: Hydrogen bond donors
   - psa: Polar surface area (Å²)
   - rtb: Rotatable bonds
   - num_ro5_violations: Lipinski rule-of-five violations
   - aromatic_rings: Number of aromatic rings
   - heavy_atoms: Number of non-hydrogen atoms
   - qed_weighted: Drug-likeness score (0-1)
   - mw_freebase: Molecular weight without salt

2. BIOACTIVITY DATA (from activity endpoint):
   - standard_value: IC50, EC50, Ki, Kd values
   - standard_units: nM, uM, pM
   - standard_type: IC50, EC50, Ki, Kd, %inhibition
   - pchembl_value: -log(molar IC50/Ki/EC50)
   - activity_comment: Active, Inactive, Inconclusive
   - target_chembl_id: Target protein identifier
   - target_pref_name: Target protein name
   - assay_chembl_id: Assay identifier
   - assay_description: Assay protocol details
   - document_chembl_id: Source publication

3. STRUCTURAL INFORMATION (from molecule endpoint):
   - molecule_structures.canonical_smiles: Canonical SMILES
   - molecule_structures.standard_inchi: InChI string
   - molecule_structures.standard_inchi_key: InChI key
   - molecule_structures.molfile: MOL file format

4. DRUG INFORMATION (from molecule endpoint):
   - pref_name: Preferred drug name
   - max_phase: Highest clinical trial phase (0-4)
   - first_approval: Year of first approval
   - oral: Boolean for oral administration
   - parenteral: Boolean for injection
   - topical: Boolean for topical use
   - black_box_warning: Boolean for safety warnings
   - availability_type: -1=discontinued, 0=experimental, 1=prescription, 2=OTC
   - withdrawn_flag: Boolean if withdrawn from market

5. TARGET INFORMATION (from target endpoint via activity):
   - target_type: SINGLE PROTEIN, PROTEIN COMPLEX, etc.
   - organism: Homo sapiens, Mus musculus, etc.
   - target_components: Gene names, UniProt IDs

6. COMPUTED FEATURES (can be derived from SMILES using RDKit):
   - Morgan fingerprints (ECFP4, ECFP6)
   - MACCS keys (166-bit fingerprint)
   - Topological descriptors
   - 3D descriptors (if conformer generated)
   - Substructure counts (rings, chains, functional groups)

===================================================================================
EXAMPLE QUERIES TO ChEMBL API
===================================================================================

Search by name:
    GET https://www.ebi.ac.uk/chembl/api/data/molecule?pref_name__iexact=aspirin

Search by SMILES:
    GET https://www.ebi.ac.uk/chembl/api/data/molecule?molecule_structures__canonical_smiles__flexmatch=CC(=O)O

Get IC50 data for a molecule:
    GET https://www.ebi.ac.uk/chembl/api/data/activity?molecule_chembl_id=CHEMBL25&standard_type=IC50

Get all activity data for a target:
    GET https://www.ebi.ac.uk/chembl/api/data/activity?target_chembl_id=CHEMBL2047&standard_type=IC50

===================================================================================
"""

import requests
import json
import pandas as pd
from typing import List, Dict, Any, Optional

# ============================
# API Endpoints
# ============================
OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_URL = "https://www.ebi.ac.uk/chembl/api/data"

# ============================
# Utility Functions
# ============================

def query_open_targets(query: str, variables: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
    """
    Send a GraphQL query to the Open Targets Platform API with retry logic.
    
    GraphQL is a query language that allows you to request exactly the data you need.
    This function constructs a POST request with the query and variables, sends it
    to the Open Targets API, and returns the JSON response.

    Args:
        query (str): GraphQL query string defining what data to retrieve.
                    Should include the query structure with fields and subfields.
        variables (dict, optional): Dictionary of variables to pass to the query.
                                   Allows parameterization of queries. Defaults to None.
        max_retries (int, optional): Number of retry attempts on server errors. Defaults to 3.

    Returns:
        dict: JSON response from the API containing the requested data.
              Structure: {"data": {...}, "errors": [...] (if any)}

    Example:
        >>> query = "{ target(ensemblId: \\"ENSG00000139618\\") { approvedSymbol } }"
        >>> result = query_open_targets(query)
        >>> print(result["data"]["target"]["approvedSymbol"])
        'BRCA2'
    
    Notes:
        - The API endpoint is defined in OPEN_TARGETS_URL global variable
        - This function will return errors in the response if query is malformed
        - Network errors will raise requests.HTTPError after retries
        - Implements exponential backoff on 502/503 errors
    """
    # Construct the payload with query and optional variables
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    # Retry logic for handling temporary server errors
    for attempt in range(max_retries):
        try:
            # Send POST request to the GraphQL endpoint
            response = requests.post(OPEN_TARGETS_URL, json=payload, timeout=30)
            response.raise_for_status()  # Raise error for bad status codes (4xx, 5xx)
            
            # Parse and return JSON response
            data = response.json()
            return data
            
        except requests.exceptions.HTTPError as e:
            # Check if it's a temporary server error (502, 503, 504)
            if response.status_code in [502, 503, 504] and attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"      ⚠ Server error {response.status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                # Re-raise if not retryable or out of retries
                raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"      ⚠ Network error, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                raise
    
    # This should never be reached due to the raise in the loop
    raise Exception("Max retries exceeded")


def query_chembl(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Send a GET request to the ChEMBL REST API.
    
    ChEMBL provides a RESTful API for accessing bioactivity data, molecular properties,
    and drug information. This function constructs the full URL, adds query parameters,
    and returns the parsed JSON response.

    Args:
        endpoint (str): API endpoint to query (e.g., 'activity', 'molecule', 'target').
                       This is appended to the base CHEMBL_URL.
        params (dict, optional): Query parameters to filter results.
                                Common params: molecule_chembl_id, target_chembl_id,
                                standard_type, limit, offset. Defaults to None.

    Returns:
        dict: JSON response from the ChEMBL API.
              Structure varies by endpoint but typically includes a list of results.

    Example:
        >>> params = {"molecule_chembl_id": "CHEMBL25", "standard_type": "IC50"}
        >>> result = query_chembl("activity", params)
        >>> print(len(result["activities"]))
        42
    
    Notes:
        - ChEMBL API returns paginated results (default 20 items)
        - Use 'limit' and 'offset' params for pagination
        - Results are in JSON format by default
        - API documentation: https://chembl.gitbook.io/chembl-interface-documentation/
    """
    # Construct full URL by combining base URL and endpoint
    # Add .json extension for JSON format response
    if endpoint.endswith(".json"):
        url = f"{CHEMBL_URL}/{endpoint}"
    elif "/" in endpoint and "molecule/" in endpoint:
        # For molecule/{id} endpoints, add .json at the end
        url = f"{CHEMBL_URL}/{endpoint}.json"
    else:
        # For activity and other endpoints, add .json
        url = f"{CHEMBL_URL}/{endpoint}.json"
    
    # Send GET request with query parameters
    response = requests.get(url, params=params)
    response.raise_for_status()  # Raise error for bad status codes
    
    # Parse and return JSON response
    return response.json()


# ============================
# Step 1: Disease → EFO ID
# ============================

def map_disease_to_efo(disease_name: str) -> List[str]:
    """
    Map a free-text disease name to EFO (Experimental Factor Ontology) identifiers.
    
    The EFO is a systematic description of experimental variables in biological systems.
    This function uses the Open Targets mapIds endpoint to convert common disease names
    (e.g., "asthma", "diabetes") into standardized EFO identifiers that can be used
    throughout the Open Targets Platform.
    
    The function searches for disease entities only and returns all matching EFO IDs.
    Multiple IDs may be returned for diseases with subtypes or related conditions.

    Args:
        disease_name (str): Common disease name to search for.
                           Examples: 'asthma', 'type 2 diabetes', 'breast cancer'
                           Case-insensitive, partial matches may work.

    Returns:
        list: List of EFO IDs (strings) that match the input term.
             Format: ['EFO_0000270', 'EFO_1002040']
             Empty list if no matches found.

    Example:
        >>> efo_ids = map_disease_to_efo('asthma')
        >>> print(efo_ids)
        ['EFO_0000270']
        
        >>> efo_ids = map_disease_to_efo('type 2 diabetes')
        >>> print(efo_ids)
        ['EFO_0001360']
    
    Notes:
        - Based on the schema: mapIds returns MappingResults with mappings array
        - Each mapping has: term (input) and hits (array of matched entities)
        - Each hit has: id (EFO ID) and entity (type, should be 'disease')
        - The function filters to ensure only disease entities are returned
        - EFO IDs use underscore format: EFO_1234567
    """
    # Construct GraphQL query using the mapIds endpoint
    # This query requests mappings for disease entities only
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
    
    # Set variables: search for the disease name, restrict to "disease" entity type
    variables = {
        "terms": [disease_name],
        "entityNames": ["disease"]
    }
    
    # Execute the query
    data = query_open_targets(query, variables)

    # Extract EFO IDs from the response
    efo_ids = []
    
    # Navigate through the response structure
    # data["data"]["mapIds"]["mappings"] is a list of mapping results
    for mapping in data["data"]["mapIds"]["mappings"]:
        # Each mapping has "hits" - matched entities for the search term
        for hit in mapping["hits"]:
            # Verify it's a disease entity and add the ID
            if hit["entity"] == "disease":
                efo_ids.append(hit["id"])
    
    return efo_ids

# ============================
# Step 2: Disease → Target Proteins
# ============================

def get_associated_targets(efo_id: str, max_targets: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieve target proteins (genes) associated with a specific disease.
    
    This function queries the Open Targets Platform to find genes/proteins that are
    associated with a disease based on multiple lines of evidence including:
    - Genetic associations (GWAS)
    - Somatic mutations (cancer)
    - Known drug mechanisms
    - Animal models
    - Literature mining
    - Pathways and systems biology
    
    Each target receives an association score (0-1) indicating the strength of evidence
    linking it to the disease. Higher scores indicate stronger associations based on
    multiple datasources.

    Args:
        efo_id (str): EFO identifier for the disease (e.g., 'EFO_0000270' for asthma).
                     Must be a valid EFO ID from the disease ontology.
        max_targets (int, optional): Maximum number of targets to retrieve.
                                    Defaults to 50. API limit is typically 10,000.

    Returns:
        list: List of dictionaries, each containing:
             - 'target_id' (str): Ensembl gene ID (e.g., 'ENSG00000169083')
             - 'approved_symbol' (str): HGNC gene symbol (e.g., 'AR')
             - 'association_score' (float): Overall score (0-1) for target-disease association

    Example:
        >>> targets = get_associated_targets('EFO_0000270', max_targets=5)
        >>> for target in targets:
        ...     print(f"{target['approved_symbol']}: {target['association_score']:.3f}")
        IL13: 0.856
        GATA3: 0.782
        IL4R: 0.731
    
    Notes:
        - Results are ordered by association_score (highest first)
        - Uses pagination to retrieve all targets up to max_targets
        - Each page returns up to 50 results (API limitation)
        - Association scores are computed from multiple datasources
        - The function aggregates results across multiple pages if needed
    """
    # Construct GraphQL query to get associated targets for a disease
    # Uses pagination parameters: pageIndex and pageSize
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
    
    # Initialize variables for pagination
    targets = []          # Accumulator for all targets
    page_index = 0        # Current page (0-indexed)
    page_size = 50        # Maximum items per page (API limit)

    # Paginate through results until we have enough targets or run out of data
    while len(targets) < max_targets:
        # Set query variables for this page
        variables = {
            "efoId": efo_id,
            "pageIndex": page_index,
            "pageSize": page_size
        }
        
        # Execute the query
        data = query_open_targets(query, variables)
        
        # Extract rows from response
        rows = data["data"]["disease"]["associatedTargets"]["rows"]
        
        # If no rows returned, we've exhausted all results
        if not rows:
            break
        
        # Process each target in the page
        for row in rows:
            targets.append({
                "target_id": row["target"]["id"],
                "approved_symbol": row["target"]["approvedSymbol"],
                "association_score": row["score"]
            })
        
        # Move to next page
        page_index += 1
        
        # If we got fewer results than page_size, there are no more pages
        if len(rows) < page_size:
            break

    # Return only the requested number of targets (slice if we got more)
    return targets[:max_targets]

# ============================
# Step 3: Target → Known Drugs
# ============================

def get_known_drugs_for_target(target_id: str, max_drugs: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch known drugs (molecules) that modulate a specific target protein.
    
    This function retrieves drugs with curated mechanisms of action targeting the
    specified gene/protein. Drugs are filtered to include investigational and approved
    compounds that have been shown to interact with the target through experimental
    evidence or clinical trials.
    
    The data includes:
    - Clinical precedence (phase of development)
    - Drug identifiers (ChEMBL IDs)
    - Preferred drug names
    - Clinical development phase

    Args:
        target_id (str): Ensembl gene ID for the target (e.g., 'ENSG00000169083').
                        Must be a valid Ensembl ID from the human genome assembly.
        max_drugs (int, optional): Maximum number of drugs to retrieve.
                                  Defaults to 50. Use higher values for comprehensive data.

    Returns:
        list: List of dictionaries, each containing:
             - 'drug_id' (str): ChEMBL molecule ID (e.g., 'CHEMBL941')
             - 'pref_name' (str): Preferred drug name (e.g., 'BICALUTAMIDE')
             - 'phase' (float): Maximum clinical trial phase reached
                  Values: -1 (Unknown), 0 (Phase 0), 1 (Phase I), 
                         2 (Phase II), 3 (Phase III), 4 (Phase IV/Approved)

    Example:
        >>> drugs = get_known_drugs_for_target('ENSG00000169083', max_drugs=3)
        >>> for drug in drugs:
        ...     phase_label = {4: 'Approved', 3: 'Phase III', 2: 'Phase II', 
        ...                    1: 'Phase I'}[drug['phase']]
        ...     print(f"{drug['pref_name']} ({drug['drug_id']}): {phase_label}")
        BICALUTAMIDE (CHEMBL941): Approved
        ENZALUTAMIDE (CHEMBL1261078): Approved
        APALUTAMIDE (CHEMBL3301610): Approved
    
    Notes:
        - Uses cursor-based pagination (more efficient than offset pagination)
        - Results are ordered by clinical phase (approved drugs first)
        - Includes drugs at all development stages (preclinical to approved)
        - Each drug may target multiple proteins (polypharmacology)
        - Drug phase encoding: 4=Approved, 3=Phase III, 2=Phase II, 1=Phase I, 0=Phase 0, -1=Unknown
    """
    # Construct GraphQL query to get known drugs for a target
    # Uses cursor-based pagination for efficient data retrieval
    query = """
        query KnownDrugs($targetId: String!, $size: Int!, $cursor: String) {
            target(ensemblId: $targetId) {
                knownDrugs(size: $size, cursor: $cursor) {
                    count
                    cursor
                    rows {
                        drugId
                        prefName
                        phase
                    }
                }
            }
        }
    """
    
    # Initialize variables for pagination
    drugs = []          # Accumulator for all drugs
    cursor = None       # Opaque cursor for pagination (starts as None)
    size = 50           # Number of results per request

    # Paginate through results using cursor-based pagination
    while len(drugs) < max_drugs:
        # Set query variables for this page
        variables = {
            "targetId": target_id,
            "size": size,
            "cursor": cursor  # None for first page, then updated from response
        }
        
        # Execute the query
        data = query_open_targets(query, variables)
        
        # Extract known drugs data from response
        known_drugs = data["data"]["target"]["knownDrugs"]
        
        # Process each drug in the response
        for row in known_drugs["rows"]:
            drugs.append({
                "drug_id": row["drugId"],
                "pref_name": row["prefName"],
                "phase": row["phase"]
            })
        
        # Get cursor for next page (None if no more pages)
        cursor = known_drugs.get("cursor")
        
        # If cursor is None, we've retrieved all available data
        if not cursor:
            break

    # Return only the requested number of drugs (slice if we got more)
    return drugs[:max_drugs]

# ============================
# Step 4: Drug → IC50 Data (ChEMBL)
# ============================

def get_ic50_data_for_molecule(molecule_chembl_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Retrieve IC50 bioactivity records for a specific molecule from ChEMBL database.
    
    IC50 (half maximal inhibitory concentration) is a quantitative measure indicating
    how much drug is needed to inhibit a biological process by 50%. This is one of the
    most important metrics in drug discovery for assessing drug potency.
    
    This function queries the ChEMBL activity endpoint to get all IC50 measurements
    for a given drug molecule across different targets, assays, and conditions. The
    data includes the measured value, units, target information, and assay details.

    Args:
        molecule_chembl_id (str): ChEMBL molecule identifier (e.g., 'CHEMBL25').
                                 Must be a valid ChEMBL ID for a small molecule.
        limit (int, optional): Maximum number of IC50 records to retrieve.
                              Defaults to 100. ChEMBL may have 1000s of records per drug.

    Returns:
        list: List of IC50 bioactivity records. Each dictionary contains:
             - 'molecule_chembl_id' (str): Input molecule ID
             - 'standard_value' (float): IC50 value in standard_units
             - 'standard_units' (str): Typically 'nM' (nanomolar)
             - 'target_chembl_id' (str): ChEMBL ID of the target protein
             - 'target_pref_name' (str): Target protein name
             - 'assay_chembl_id' (str): ChEMBL assay ID
             - 'pchembl_value' (float): -log10(molar IC50), normalized potency
             - 'document_chembl_id' (str): Publication reference

    Example:
        >>> ic50_data = get_ic50_data_for_molecule('CHEMBL941', limit=5)
        >>> for record in ic50_data:
        ...     print(f"Target: {record['target_pref_name']}")
        ...     print(f"IC50: {record['standard_value']} {record['standard_units']}")
        ...     print(f"pIC50: {record['pchembl_value']}")
        ...     print("---")
        Target: Androgen Receptor
        IC50: 156.0 nM
        pIC50: 6.81
        ---
    
    Notes:
        - Only returns records with numeric standard_value (filters out nulls)
        - Standard units are typically nM, but can be uM, pM, M
        - pchembl_value is the negative log of molar IC50 (higher = more potent)
        - Same molecule may have multiple IC50 values for same target (different assays)
        - Filters specifically for standard_type='IC50' (not EC50, Ki, etc.)
        - Results are paginated starting at offset 0
    """
    # Use pagination to gather up to `limit` records
    page_limit = min(100, limit)  # ChEMBL often restricts page sizes; use 100 per page
    offset = 0
    ic50_records = []

    while len(ic50_records) < limit:
        params = {
            "molecule_chembl_id": molecule_chembl_id,
            "standard_type__exact": "IC50",
            "limit": page_limit,
            "offset": offset
        }
        try:
            data = query_chembl("activity", params)
        except Exception as e:
            print(f"      ❌ Error querying ChEMBL for IC50 data ({molecule_chembl_id}): {e}")
            break

        activities = data.get("activities", [])
        if not activities:
            break

        for activity in activities:
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
            if len(ic50_records) >= limit:
                break

        if len(activities) < page_limit:
            break
        offset += page_limit

    return ic50_records

# ============================
# Step 5: Drug → Molecular Features (ChEMBL)
# ============================

def get_molecule_properties(molecule_chembl_id: str) -> Dict[str, Any]:
    data = query_chembl(f"molecule/{molecule_chembl_id}")
    # with open(f"{molecule_chembl_id}_raw.json", "w", encoding="utf-8") as f:
    #     json.dump(data, f, indent=2)
    
    props = data.get("molecule_properties", {})
    structs = data.get("molecule_structures", {})

    return {
        "chembl_id": data.get("molecule_chembl_id"),
        "max_phase": data.get("max_phase"),
        "molecular_formula": props.get("full_molformula"),
        "molecular_weight": props.get("full_mwt"),
        "alogp": props.get("alogp"),
        "aromatic_rings": props.get("aromatic_rings"),
        "mw_freebase" : props.get("mw_freebase"),
        "hba": props.get("hba"),
        "hbd": props.get("hbd"),
        "heavy_atoms": props.get("heavy_atoms"),
        "np_likeness_score": props.get("np_likeness_score"),
        "num_ro5_violations": props.get("num_ro5_violations"),
        "psa": props.get("psa"),
        "qed_weighted": props.get("qed_weighted"),
        "ro3_pass": props.get("ro3_pass"),
        "rtb": props.get("rtb"),
        "smiles": structs.get("canonical_smiles"),
        "inchi": structs.get("standard_inchi"),
        "inchi_key": structs.get("standard_inchi_key"),
        "molfile_preview": structs.get("molfile", "") if structs.get("molfile") else None
    }
    
# ============================
# Main Pipeline
# ============================

def pipeline(disease_name: str, max_targets: int = 5, max_drugs_per_target: int = 5) -> pd.DataFrame:
    """
    Execute the complete Disease → Target → Drug → IC50 → Features pipeline.
    
    This is the main orchestration function that calls all the previous functions in
    sequence to build a comprehensive dataset for IC50 prediction modeling. The pipeline
    follows this workflow:
    
    1. Disease Mapping: Convert disease name to EFO ID
    2. Target Discovery: Find genes/proteins associated with the disease
    3. Drug Discovery: Find known drugs targeting each protein
    4. Bioactivity Data: Retrieve IC50 measurements for each drug
    5. Feature Extraction: Get molecular properties for each drug
    6. Data Integration: Combine all information into a single DataFrame
    
    The resulting dataset contains one row per IC50 measurement, with columns for
    disease, target, drug, bioactivity, and molecular features. This format is ideal
    for training machine learning models to predict IC50 values.

    Args:
        disease_name (str): Input disease name for the pipeline (e.g., 'asthma').
                           Can be any common disease name that maps to EFO.
        max_targets (int, optional): Maximum number of target proteins to process.
                                     Defaults to 5. Higher values = more data but slower.
        max_drugs_per_target (int, optional): Maximum drugs per target to process.
                                             Defaults to 5. Controls dataset size.

    Returns:
        pandas.DataFrame: Combined dataset with all retrieved data.
                         Columns include:
                         - disease_name: Input disease name
                         - efo_id: EFO disease identifier
                         - target_id: Ensembl gene ID
                         - target_symbol: Gene symbol (e.g., 'BRCA2')
                         - association_score: Target-disease association strength
                         - drug_id: ChEMBL molecule ID
                         - drug_name: Preferred drug name
                         - clinical_phase: Development phase (0-4)
                         - ic50_value: IC50 measurement value
                         - ic50_units: Units (typically nM)
                         - target_chembl_id: ChEMBL target ID
                         - assay_chembl_id: ChEMBL assay ID
                         - pchembl_value: Normalized potency (-log IC50)
                         - pref_name: Drug name (from features)
                         - full_mwt: Molecular weight
                         - alogp: LogP (lipophilicity)
                         - hba: Hydrogen bond acceptors
                         - hbd: Hydrogen bond donors
                         - psa: Polar surface area
                         - rtb: Rotatable bonds
                         - ro5_violations: Lipinski violations
                         - qed_weighted: Drug-likeness score

    Example:
        >>> df = pipeline("breast cancer", max_targets=3, max_drugs_per_target=2)
        >>> print(df.shape)
        (45, 23)
        >>> print(df.columns.tolist())
        ['disease_name', 'efo_id', 'target_id', ...]
        >>> print(df['ic50_value'].describe())
        count    45.0
        mean     234.5
        std      567.2
        min      0.5
        max      5000.0
    
    Notes:
        - Progress is printed to console for each step
        - Empty DataFrame is returned if disease name not found
        - Processing time scales with max_targets × max_drugs_per_target
        - Typical run: 3 targets × 5 drugs = 15 drugs × ~10 IC50s = ~150 rows
        - Some drugs may have no IC50 data (will be skipped)
        - All data is aggregated before returning (no intermediate files)
    """
    # ================================================================================
    # STEP 1: Map disease name to EFO identifier
    # ================================================================================
    print(f"\n{'='*80}")
    print(f"STEP 1: Mapping disease name '{disease_name}' to EFO ID(s)...")
    print(f"{'='*80}")
    
    efo_ids = map_disease_to_efo(disease_name)
    
    # Check if mapping was successful
    if not efo_ids:
        print("❌ No EFO ID found for the given disease name.")
        print("   Try a different disease name or check spelling.")
        return pd.DataFrame()
    
    # Use the first matching EFO ID (highest relevance)
    efo_id = efo_ids[0]
    print(f"✓ Using EFO ID: {efo_id}")
    if len(efo_ids) > 1:
        print(f"  Note: Found {len(efo_ids)} matches, using the first one.")
        print(f"  Other matches: {', '.join(efo_ids[1:])}")

    # ================================================================================
    # STEP 2: Retrieve associated targets (genes/proteins) for the disease
    # ================================================================================
    print(f"\n{'='*80}")
    print(f"STEP 2: Retrieving associated targets for {efo_id}...")
    print(f"{'='*80}")
    
    targets = get_associated_targets(efo_id, max_targets=max_targets)
    print(f"✓ Found {len(targets)} target(s).")
    
    # Display target information
    if targets:
        print(f"\n  Top targets by association score:")
        for i, target in enumerate(targets[:5], 1):  # Show top 5
            print(f"    {i}. {target['approved_symbol']:10s} "
                  f"({target['target_id']:20s}) "
                  f"Score: {target['association_score']:.3f}")

    # ================================================================================
    # STEP 3-5: For each target, get drugs, IC50 data, and molecular features
    # ================================================================================
    all_data = []  # Master list to store all rows
    
    # Iterate through each target
    for i, target in enumerate(targets, 1):
        print(f"\n{'='*80}")
        print(f"Processing target {i}/{len(targets)}: "
              f"{target['approved_symbol']} ({target['target_id']})")
        print(f"{'='*80}")
        
        # ----------------------------------------------------------------------------
        # STEP 3: Fetch known drugs for this target
        # ----------------------------------------------------------------------------
        print(f"  STEP 3: Fetching known drugs for target...")
        try:
            drugs = get_known_drugs_for_target(target["target_id"], max_drugs=max_drugs_per_target)
        except Exception as e:
            print(f"  ❌ Error fetching known drugs for target {target['target_id']}: {e}")
            continue

        if not drugs:
            print(f"  ⚠ No drugs found for this target, skipping...")
            continue
        print(f"  ✓ Found {len(drugs)} drug(s).")

        # Iterate through each drug for this target
        for j, drug in enumerate(drugs, 1):
            print(f"\n    {'─'*76}")
            print(f"    Processing drug {j}/{len(drugs)}: "
                  f"{drug['pref_name']} ({drug['drug_id']})")
            print(f"    Clinical Phase: {drug['phase']}")
            print(f"    {'─'*76}")
            
            # ------------------------------------------------------------------------
            # STEP 4: Retrieve IC50 data from ChEMBL
            # ------------------------------------------------------------------------
            print(f"      STEP 4: Retrieving IC50 data from ChEMBL...")
            try:
                ic50_data = get_ic50_data_for_molecule(drug["drug_id"], limit=100)
            except Exception as e:
                print(f"      ❌ Error retrieving IC50 data for {drug['drug_id']}: {e}")
                continue
            print(f"      ✓ Found {len(ic50_data)} IC50 record(s).")

            # ------------------------------------------------------------------------
            # STEP 5: Fetch molecular features/properties
            # ------------------------------------------------------------------------
            print(f"      STEP 5: Fetching molecular features...")
            try:
                features = get_molecule_properties(drug["drug_id"])
            except Exception as e:
                print(f"      ❌ Error fetching molecular features for {drug['drug_id']}: {e}")
                continue

            if not features or not isinstance(features, dict):
                print(f"      ⚠ No molecular features found for this drug, skipping...")
                continue

            # Require SMILES for downstream chemistry
            if not features.get("smiles"):
                print(f"      ⚠ No SMILES available for {drug['drug_id']} ({drug['pref_name']}), skipping...")
                continue

            print(f"      ✓ Retrieved properties: MW={features.get('molecular_weight') or features.get('full_mwt')}, "
                  f"LogP={features.get('alogp')}, "
                  f"HBA={features.get('hba')}, "
                  f"HBD={features.get('hbd')}")

            # ------------------------------------------------------------------------
            # DATA INTEGRATION: Combine all information for each IC50 record
            # ------------------------------------------------------------------------
            # Each IC50 measurement becomes one row in the final dataset
            for ic50 in ic50_data:
                row = {
                    # Disease information
                    "disease_name": disease_name,
                    "efo_id": efo_id,
                    
                    # Target information
                    "target_id": target["target_id"],
                    "target_symbol": target["approved_symbol"],
                    "association_score": target["association_score"],
                    
                    # Drug information
                    "drug_id": drug["drug_id"],
                    "drug_name": drug["pref_name"],
                    "clinical_phase": drug["phase"],
                    
                    # IC50 bioactivity data
                    "ic50_value": ic50["standard_value"],
                    "ic50_units": ic50["standard_units"],
                    "target_chembl_id": ic50["target_chembl_id"],
                    "assay_chembl_id": ic50["assay_chembl_id"],
                    "pchembl_value": ic50["pchembl_value"]
                }
                
                # Add molecular features to the row (only non-None values)
                # This prevents empty columns in the CSV output
                for key, value in features.items():
                    if value is not None and key != "molecule_chembl_id":
                        row[key] = value
                
                # Add row to master list
                all_data.append(row)
            
            if ic50_data:
                print(f"      ✓ Added {len(ic50_data)} rows to dataset")
            else:
                print(f"      ⚠ No IC50 data available for this drug")

    # ================================================================================
    # FINAL STEP: Convert to DataFrame and return
    # ================================================================================
    print(f"\n{'='*80}")
    print("Pipeline completed successfully!")
    print(f"{'='*80}")
    
    return pd.DataFrame(all_data)

# ============================
# Example Usage & Discussion
# ============================

def collect_large_dataset(diseases: List[str], max_targets: int = 50, max_drugs_per_target: int = 10, 
                         output_file: str = "ic50_large_dataset.csv") -> pd.DataFrame:
    """
    Collect IC50 data across multiple diseases for large-scale model training.
    
    This function orchestrates the pipeline across multiple diseases, aggregating
    all IC50 records into a single comprehensive dataset. It's designed for
    collecting 10,000+ records by processing multiple diseases in sequence.
    
    Features incremental saving: saves CSV after each disease to prevent data loss.
    
    Args:
        diseases (list): List of disease names to process
        max_targets (int, optional): Max targets per disease. Defaults to 50.
        max_drugs_per_target (int, optional): Max drugs per target. Defaults to 10.
        output_file (str, optional): CSV filename for incremental saves. Defaults to "ic50_large_dataset.csv".
    
    Returns:
        pd.DataFrame: Combined dataset with IC50 records from all diseases
    """
    all_dataframes = []
    total_records = 0
    
    for i, disease in enumerate(diseases, 1):
        print(f"\n{'#'*80}")
        print(f"# Processing Disease {i}/{len(diseases)}: {disease.upper()}")
        print(f"{'#'*80}")
        
        try:
            # Run pipeline for this disease
            df = pipeline(disease, max_targets=max_targets, max_drugs_per_target=max_drugs_per_target)
            
            if not df.empty:
                all_dataframes.append(df)
                total_records += len(df)
                print(f"\n✓ Collected {len(df)} IC50 records from {disease}")
                print(f"  Total so far: {total_records} records")
                
                # Incremental save: save progress after each disease
                if all_dataframes:
                    temp_df = pd.concat(all_dataframes, ignore_index=True)
                    temp_df.to_csv(output_file, index=False)
                    print(f"  💾 Progress saved to {output_file} ({total_records} records)")
            else:
                print(f"\n⚠ No IC50 data collected for {disease}")
                
        except Exception as e:
            print(f"\n❌ Error processing {disease}: {str(e)}")
            print(f"  Continuing with next disease...")
            # Save progress so far before continuing
            if all_dataframes:
                temp_df = pd.concat(all_dataframes, ignore_index=True)
                temp_df.to_csv(output_file, index=False)
                print(f"  💾 Progress saved to {output_file} ({total_records} records)")
            continue
    
    # Combine all dataframes
    if all_dataframes:
        final_df = pd.concat(all_dataframes, ignore_index=True)
        return final_df
    else:
        return pd.DataFrame()


def main():
    """
    Collect large-scale IC50 dataset across multiple diseases.
    """
    print("\n" + "="*80)
    print("LARGE-SCALE IC50 DATA COLLECTION")
    print("="*80)
    print("\nTarget: Collect 15,000+ IC50 records")
    print("\nConfiguration:")
    print("  • Diseases: 7 different diseases")
    print("  • Max targets per disease: 50")
    print("  • Max drugs per target: 10")
    print("  • Max IC50 per drug: 100")
    print("  • Expected total: 15,000-35,000 IC50 records")
    print("\nEstimated time: 20-40 minutes")
    print("Output: ic50_large_dataset.csv (saved incrementally)")
    print("="*80)
    
    # Diseases with good small molecule drug coverage (increased to 7)
    diseases = [
        "breast cancer",
        "prostate cancer",
        "lung cancer",
        "colorectal cancer",
        "diabetes type 2",
        "hypertension",
        "alzheimer disease"
    ]
    
    # Collect data across all diseases with incremental saving
    df = collect_large_dataset(diseases, max_targets=50, max_drugs_per_target=10, 
                              output_file="ic50_large_dataset.csv")

    if df.empty:
        print("\n❌ No data retrieved. Exiting.")
        return

    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    print(f"\n📊 Total IC50 records collected: {len(df)}")
    print(f"   • Unique drugs: {df['drug_id'].nunique()}")
    print(f"   • Unique targets: {df['target_id'].nunique()}")
    print(f"   • Diseases covered: {df['disease_name'].nunique()}")
    
    print(f"\n📋 Sample data (first 10 rows):")
    display_cols = ['disease_name', 'target_symbol', 'drug_name', 'ic50_value', 'ic50_units', 'pchembl_value']
    available_cols = [col for col in display_cols if col in df.columns]
    print(df[available_cols].head(10).to_string(index=False))
    
    # Save to CSV
    output_file = "ic50_large_dataset.csv"
    df.to_csv(output_file, index=False)
    print(f"\n💾 Large dataset saved to '{output_file}'")
    print(f"   File contains {len(df)} IC50 records across {df['drug_id'].nunique()} drugs")
    
    # Statistics
    print(f"\n📈 IC50 Value Statistics:")
    print(df['ic50_value'].describe().to_string())
    
    print(f"\n🎯 Top 10 Targets by Number of IC50 Records:")
    target_counts = df.groupby(['target_symbol', 'target_id']).size().sort_values(ascending=False).head(10)
    for (symbol, target_id), count in target_counts.items():
        print(f"   {symbol:15s} {count:4d} IC50 records")
    
    print(f"\n💊 Top 10 Drugs by Number of IC50 Records:")
    drug_counts = df.groupby(['drug_name', 'drug_id']).size().sort_values(ascending=False).head(10)
    for (name, drug_id), count in drug_counts.items():
        print(f"   {name[:30]:30s} {count:4d} IC50 records")
    
    print("\n" + "="*80)
    print("LARGE-SCALE DATA COLLECTION COMPLETED!")
    print("="*80)
    print(f"\nYou now have {len(df)} IC50 records ready for model training! 🚀")


if __name__ == "__main__":
    main()