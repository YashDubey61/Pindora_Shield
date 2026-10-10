import torch
from .mol_metrics import Tokenizer
from .generator import GeneratorModel, GenSampler

# ----------------------------
# 1. Load Tokenizer
# ----------------------------
tokenizer = Tokenizer()
tokenizer.build_vocab()
n_tokens = tokenizer.n_tokens

# ----------------------------
# 2. Load Pretrained Generator Model
# ----------------------------
model_path = r"res/save_models/ZINC/TenGAN_0.5/rollout_8/batch_64/druglikeness/g_pretrained.pkl"

print("Loading pretrained model:", model_path)

model = GeneratorModel(
    n_tokens=n_tokens,
    d_model=256,               # correct for the checkpoint
    nhead=4,                   # correct for the checkpoint
    num_encoder_layers=4,
    dim_feedforward=1024,      # VERY IMPORTANT FIX
    dropout=0.1,
    activation="relu",
    max_length=200
)

state = torch.load(model_path, map_location="cpu")
model.load_state_dict(state, strict=True)
model.eval()

print("Model loaded successfully!")

# ----------------------------
# 3. Sampling Setup
# ----------------------------
sampler = GenSampler(
    model=model,
    tokenizer=tokenizer,
    batch_size=8,
    max_len=120
)

# ----------------------------
# 4. Generate SMILES
# ----------------------------
print("\nGenerating molecules...\n")
samples = sampler.sample_multi(40)   # 40 SMILES generate karega

# ----------------------------
# 5. Print Results
# ----------------------------
print("\nGenerated Molecules:")
for smi in samples:
    print(smi)

# Save to file
with open("generated_smiles.txt", "w") as f:
    for s in samples:
        f.write(s + "\n")

print("\nSaved to generated_smiles.txt")
