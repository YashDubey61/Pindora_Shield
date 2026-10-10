import uuid
import json
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from models.schemas import (
    TextInput, TextResponse, Generate3DInput, Generate3DResponse,
    ScaffoldInfoInput, ScaffoldInfoResponse,
)
from utils.generate_3d import Molecule3DGenerator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["pindora"],
    responses={404: {"description": "Not found"}},
)


def _run_drug_discovery(pindora_instance, text: str):
    """Blocking wrapper executed in a thread via asyncio.to_thread."""
    return pindora_instance.drug_discovery_pipeline(text)


@router.post("/drug_discovery", response_model=TextResponse)
async def process_text(request: TextInput, req: Request):
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    logger.info("Received drug discovery request: %s", request.text[:100])

    # Use the shared Pindora instance loaded at startup (Fix #2)
    pindora_instance = req.app.state.pindora

    # Update in-memory job status (Fix #1)
    job_id = str(uuid.uuid4())
    req.app.state.jobs[job_id] = {"status": "in_progress", "results": None, "error": None}

    try:
        mol_gen = await asyncio.to_thread(_run_drug_discovery, pindora_instance, request.text)
        req.app.state.jobs[job_id] = {"status": "completed", "results": mol_gen, "error": None}
    except Exception as e:
        logger.exception("Drug discovery pipeline failed")
        req.app.state.jobs[job_id] = {"status": "failed", "results": None, "error": str(e)}
        raise HTTPException(status_code=500, detail=str(e))

    if not mol_gen:
        message = (
            "We need more data for this specific disease. Associated biological targets were identified, "
            "but there are currently insufficient small-molecule drug candidates or bioactivity records in public databases."
        )
    else:
        message = f"Drug discovery pipeline completed. Found {len(mol_gen)} molecule series."

    return {
        "input_text": request.text,
        "results": mol_gen,
        "status": "success",
        "message": message,
    }


@router.post("/drug_discovery_async")
async def start_drug_discovery_async(request: TextInput, req: Request):
    """Non-blocking variant: starts pipeline in background, returns a job_id
    that can be polled via /api/job_status/{job_id}.  (Fix #12)
    """
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    pindora_instance = req.app.state.pindora
    job_id = str(uuid.uuid4())
    req.app.state.jobs[job_id] = {"status": "in_progress", "results": None, "error": None}

    async def _background():
        try:
            mol_gen = await asyncio.to_thread(_run_drug_discovery, pindora_instance, request.text)
            if not mol_gen:
                msg = (
                    "We need more data for this specific disease. Associated biological targets were identified, "
                    "but there are currently insufficient small-molecule drug candidates or bioactivity records in public databases."
                )
            else:
                msg = f"Drug discovery pipeline completed. Found {len(mol_gen)} molecule series."
            req.app.state.jobs[job_id] = {"status": "completed", "results": mol_gen, "error": None, "message": msg}
            logger.info("Async job %s completed with %d results", job_id, len(mol_gen))
        except Exception as e:
            logger.exception("Async job %s failed", job_id)
            req.app.state.jobs[job_id] = {"status": "failed", "results": None, "error": str(e)}

    asyncio.create_task(_background())
    return {"job_id": job_id, "status": "in_progress"}


@router.get("/job_status/{job_id}")
async def get_job_status(job_id: str, req: Request):
    """Poll endpoint for async job status.  (Fix #12)"""
    job = req.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "completed":
        response["results"] = job["results"]
        if "message" in job:
            response["message"] = job["message"]
    elif job["status"] == "failed":
        response["error"] = job["error"]
    return response


@router.post("/generate-3d", response_model=Generate3DResponse)
async def generate_3d_endpoint(request: Generate3DInput):
    if not request.input_smile or len(request.input_smile.strip()) == 0:
        raise HTTPException(status_code=400, detail="SMILES string is required")

    try:
        generator = Molecule3DGenerator()
        result = generator._generate_3d(request.input_smile)
        return {
            "message": "3D model generated successfully",
            "file_path": result["file_path"],
            "sdf_block": result["sdf_block"],
            "num_atoms": result["num_atoms"],
            "num_bonds": result["num_bonds"],
            "status": "success",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feature 4: Scaffold alignment (Murcko, < 1ms) ────────────────────────

@router.post("/molecule/scaffold_info", response_model=ScaffoldInfoResponse)
async def scaffold_info(request: ScaffoldInfoInput):
    """Compare Bemis-Murcko scaffolds between a seed drug and a generated candidate."""
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold

        seed_mol = Chem.MolFromSmiles(request.seed_smiles)
        cand_mol = Chem.MolFromSmiles(request.candidate_smiles)
        if seed_mol is None:
            raise HTTPException(status_code=400, detail="Invalid seed SMILES")
        if cand_mol is None:
            raise HTTPException(status_code=400, detail="Invalid candidate SMILES")

        seed_scaffold = MurckoScaffold.MurckoScaffoldSmiles(
            mol=seed_mol, includeChirality=False
        )
        cand_scaffold = MurckoScaffold.MurckoScaffoldSmiles(
            mol=cand_mol, includeChirality=False
        )

        return {
            "seed_scaffold": seed_scaffold,
            "candidate_scaffold": cand_scaffold,
            "scaffold_preserved": seed_scaffold == cand_scaffold,
            "status": "success",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feature 6: SSE streaming drug discovery ───────────────────────────────

@router.get("/drug_discovery_stream")
async def drug_discovery_stream(text: str, req: Request):
    """Server-Sent Events endpoint that streams pipeline stage updates."""
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text query is required")

    pindora_instance = req.app.state.pindora

    async def event_generator():
        import os
        from pindora import _parse_disease_names

        # Stage 1: Disease resolution
        yield _sse_event(1, "Extracting target disease from query...")
        disease_json = await asyncio.to_thread(
            pindora_instance.copilot.generate_disease_name_from_prompt, text
        )
        diseases = _parse_disease_names(disease_json)
        yield _sse_event(1, f"Resolved: {', '.join(diseases) if diseases else 'none'}", done=True)

        if not diseases:
            yield _sse_data(6, "No diseases found", [])
            return

        # Stage 2–5: Full pipeline (run synchronously in thread)
        yield _sse_event(2, "Querying biological targets...")
        yield _sse_event(3, "Fetching known reference inhibitors...")
        yield _sse_event(4, "TenGAN generating novel analogs...")
        yield _sse_event(5, "Running MatriX bioactivity predictions...")

        mol_gen = await asyncio.to_thread(
            pindora_instance.drug_discovery_pipeline, diseases
        )

        yield _sse_data(6, "Complete", mol_gen)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse_event(step: int, label: str, done: bool = False) -> str:
    payload = json.dumps({"step": step, "label": label, "done": done})
    return f"data: {payload}\n\n"


def _sse_data(step: int, label: str, data) -> str:
    payload = json.dumps({"step": step, "label": label, "data": data})
    return f"data: {payload}\n\n"

