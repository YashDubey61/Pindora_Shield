import csv
from rdkit import Chem
from rdkit.Chem import AllChem

# ==============================
# FILE PATHS (change if needed)
# ==============================
GENERATED_FILE = "res/generated_smiles_ZINC.csv"
TRAIN_FILE = "dataset/ZINC.csv"
TEST_REPORT = "res/test_report.csv"

# ==============================
# Load training data
# ==============================
with open(TRAIN_FILE, "r") as f:
    train_smiles = set(line.strip() for line in f if line.strip())

# ==============================
# Load generated data (TEST SET)
# ==============================
with open(GENERATED_FILE, "r") as f:
    generated_smiles = [line.strip() for line in f if line.strip()]

print(f"Total generated test samples: {len(generated_smiles)}")

# ==============================
# TEST METRICS
# ==============================
valid_count = 0
novel_count = 0
unique_smiles = set()

results = []

for smi in generated_smiles:
    mol = Chem.MolFromSmiles(smi)

    is_valid = mol is not None and mol.GetNumAtoms() > 1
    is_novel = smi not in train_smiles

    if is_valid:
        valid_count += 1
        unique_smiles.add(smi)

    if is_valid and is_novel:
        novel_count += 1

    results.append([
        smi,
        "PASS" if is_valid else "FAIL",
        "YES" if is_novel else "NO"
    ])

# ==============================
# FINAL TEST RESULTS
# ==============================
validity = valid_count / len(generated_smiles)
uniqueness = len(unique_smiles) / max(valid_count, 1)
novelty = novel_count / max(len(unique_smiles), 1)

print("\n===== TEST RESULTS =====")
print(f"Validity     : {validity*100:.2f}%")
print(f"Uniqueness   : {uniqueness*100:.2f}%")
print(f"Novelty      : {novelty*100:.2f}%")

# ==============================
# SAVE TEST REPORT
# ==============================
with open(TEST_REPORT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["SMILES", "Validity_Test", "Novelty_Test"])
    writer.writerows(results)

print(f"\nDetailed test report saved to: {TEST_REPORT}")
