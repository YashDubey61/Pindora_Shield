from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class TextInput(BaseModel):
    text: str
    
class TextResponse(BaseModel):
    input_text: str
    results: Optional[List[Dict[str, Any]]] = None
    status: str
    message: Optional[str] = None

class Generate3DInput(BaseModel):
    input_smile: str

class Generate3DResponse(BaseModel):
    message: str
    file_path: str
    status: str
    sdf_block: Optional[str] = None
    num_atoms: Optional[int] = None
    num_bonds: Optional[int] = None

class ScaffoldInfoInput(BaseModel):
    seed_smiles: str
    candidate_smiles: str

class ScaffoldInfoResponse(BaseModel):
    seed_scaffold: str
    candidate_scaffold: str
    scaffold_preserved: bool
    status: str