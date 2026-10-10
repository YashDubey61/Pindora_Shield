import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routes.drugs import router as text_router
from routes.checks import router as check_router
from routes.metrics import router as metrics_router
from pindora import Pindora
from utils.matrix_file import MatrixPredictor

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load heavy models once at startup, share via app.state."""
    logger.info("Loading Pindora pipeline and MatriX models...")
    matrix = MatrixPredictor()
    app.state.matrix = matrix
    app.state.pindora = Pindora(matrix_predictor=matrix)
    app.state.copilot = app.state.pindora.copilot
    # In-memory job store: {job_id: {"status": str, "results": list | None, "error": str | None}}
    app.state.jobs = {}
    logger.info("Models loaded successfully.")
    yield
    logger.info("Shutting down, releasing resources.")


app = FastAPI(
    title="Pindora Shield API",
    description="Drug discovery and molecule generation API",
    version="1.0.0",
    lifespan=lifespan,
)

# Configurable CORS — defaults to ["*"] for dev, set ALLOWED_ORIGINS in production
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(text_router)
app.include_router(check_router)
app.include_router(metrics_router)
