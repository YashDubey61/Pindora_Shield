import logging
from fastapi import APIRouter, HTTPException, Request
from models.schemas import Generate3DInput
from utils.copilot import AzureOpenAIChatClient

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["pindora"],
    responses={404: {"description": "Not found"}},
)


@router.post("/metrics_data")
async def metrics_data(request: Generate3DInput, req: Request):
    if not request.input_smile or len(request.input_smile.strip()) == 0:
        raise HTTPException(status_code=400, detail="SMILES string is required")

    logger.info("Metrics request for SMILES: %s", request.input_smile[:60])

    # Use the shared MatriX instance from app.state (Fix #11 — no per-request loading)
    matrix = getattr(req.app.state, "matrix", None)
    if matrix is None:
        # Fallback: create one if state isn't populated (e.g., during testing)
        from utils.matrix_file import MatrixPredictor
        matrix = MatrixPredictor()

    # Use shared copilot client from app.state, or fallback to creating one
    client = getattr(req.app.state, "copilot", None)
    if client is None:
        client = AzureOpenAIChatClient()

    try:
        results = matrix.predict_all(request.input_smile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid SMILES: {e}")
    except Exception as e:
        logger.exception("MatriX prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")

    try:
        report = client.generate_report_from_smiles_ic50_value_association_score_target_symbol_max_phase(
            request.input_smile,
            results["IC50"],
            results["Association_Score"],
            results["Predicted_Target"],
            results["Max_Clinical_Phase"]
        )
    except Exception as e:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=f"Report generation error: {e}")

    return {
        "report": report,
        "predictions": results,
        "status": "success",
    }
