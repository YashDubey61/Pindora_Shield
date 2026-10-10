from Tengan.generate_from_smiles import MoleculeGenerator

model_path = "Tengan/res/save_models/ZINC/TenGAN_0.5/rollout_8/batch_64/druglikeness/g_pretrained.pkl"

generator = MoleculeGenerator(
    model_path=model_path,
    batch_size=8,
    max_len=120
)

input_smiles = "CCO"
num_samples = 5

results = generator.generate_from_smiles(input_smiles, num_samples)

print(f"\nGenerated {len(results)} molecules from '{input_smiles}':\n")
for i, smiles in enumerate(results, 1):
    print(f"{i}. {smiles}")
