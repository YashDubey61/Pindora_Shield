import os
import uuid
import logging
from rdkit import Chem
from rdkit.Chem import AllChem

logger = logging.getLogger(__name__)


class Molecule3DGenerator:
    def __init__(self):
        self.output_dir = "3d_models"
        os.makedirs(self.output_dir, exist_ok=True)

    def _generate_3d(self, smiles: str) -> dict:
        """Generate 3D conformer from SMILES.

        Uses robust multi-stage embedding (ETKDGv3 -> randomCoords -> heavy-atom seed)
        and UFF force-field energy minimization.
        Returns a dict with sdf_block, file_path, num_atoms, and num_bonds.
        """
        if not smiles or not isinstance(smiles, str) or not smiles.strip():
            raise ValueError("SMILES string cannot be empty")

        clean_smiles = smiles.strip()
        mol = Chem.MolFromSmiles(clean_smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES string: '{clean_smiles}'")

        mol = Chem.AddHs(mol)

        # Multi-stage robust 3D embedding
        status = -1
        # Attempt 1: Standard ETKDGv3
        try:
            status = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        except Exception:
            status = -1

        # Attempt 2: Fallback to random coordinates
        if status != 0:
            try:
                status = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
            except Exception:
                status = -1

        # Attempt 3: Embed heavy atoms first, then add coordinates for hydrogens
        if status != 0:
            try:
                mol_no_h = Chem.MolFromSmiles(clean_smiles)
                if mol_no_h:
                    status = AllChem.EmbedMolecule(mol_no_h, useRandomCoords=True, randomSeed=42)
                    if status == 0:
                        mol = Chem.AddHs(mol_no_h, addCoords=True)
            except Exception:
                status = -1

        if status != 0:
            raise RuntimeError("3D conformer embedding could not converge for this structure")

        # UFF Force-Field Energy Minimization (best-effort)
        try:
            AllChem.UFFOptimizeMolecule(mol, maxIters=500)
        except Exception as e:
            logger.debug("UFF optimization warning for %s: %s", clean_smiles, e)

        sdf_block = Chem.MolToMolBlock(mol)

        filename = f"molecule_{uuid.uuid4().hex[:8]}.sdf"
        output_path = os.path.join(self.output_dir, filename)
        try:
            writer = Chem.SDWriter(output_path)
            writer.write(mol)
            writer.close()
        except Exception as e:
            logger.warning("Could not write SDF file to disk: %s", e)

        return {
            "file_path": output_path,
            "sdf_block": sdf_block,
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
        }
