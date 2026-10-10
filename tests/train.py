import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

df = pd.read_csv("tests/use.csv")
morgan_gen = rdFingerprintGenerator.GetMorganGenerator(
    radius=2,
    fpSize=2048
)

def smiles_to_fp(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    fp = morgan_gen.GetFingerprint(mol)
    return np.array(fp)

y_ic50 = np.log10(df["ic50_value"].values)
y_association = np.log10(df["association_score"].values)
y_max_phase = df["max_phase"].values
y_target = df["target_symbol"].values

X = np.vstack(
    df["smiles"].apply(smiles_to_fp).dropna().values
)
import numpy as np
import joblib

from catboost import CatBoostRegressor, CatBoostClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import r2_score, accuracy_score

RANDOM_SEED = 42

# ==================================================
# 4️⃣ TARGET SYMBOL (FAST + LABEL ENCODER)
# ==================================================
label_encoder = LabelEncoder()
y_target_enc = label_encoder.fit_transform(y_target)

X_train, X_val, y_train, y_val = train_test_split(
    X, y_target_enc, test_size=0.2, random_state=RANDOM_SEED
)

target_model = CatBoostClassifier(
    iterations=150,        # ⬇️ reduced
    depth=5,               # ⬇️ shallower
    learning_rate=0.15,    # ⬆️ faster convergence
    loss_function="MultiClass",
    random_seed=42,
    max_ctr_complexity=1,  # 🔥 BIG SPEED BOOST
    bootstrap_type="Bernoulli",
    subsample=0.8,
    verbose=50
)

target_model.fit(
    X_train, y_train,
    eval_set=(X_val, y_val),
    early_stopping_rounds=30
)

print("Target Accuracy:", accuracy_score(
    y_val, target_model.predict(X_val))
)

joblib.dump(
    {
        "model": target_model,
        "label_encoder": label_encoder,
        "radius": 2,
        "fp_size": 2048
    },
    "catboost_target_fast.pkl"
)

print("⚡ ALL 4 QUICK MODELS TRAINED & SAVED")
