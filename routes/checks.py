import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/checks",
    tags=["pindora_check"],
    responses={404: {"description": "Not found"}},
)


@router.post("/status_checks")
async def status_checks(req: Request):
    """Return a summary of all in-memory job statuses.

    If no jobs exist, returns a default 'idle' status.
    For backward compatibility with the frontend, the response shape
    matches the original {status, message} format.
    """
    jobs = getattr(req.app.state, "jobs", {})

    if not jobs:
        return {"status": "success", "message": "Molecules are not Generating"}

    # Find the most recent job (last inserted, since dicts are ordered in 3.7+)
    latest_job_id = list(jobs.keys())[-1]
    latest = jobs[latest_job_id]

    status_map = {
        "in_progress": "Molecules Generation in Progress",
        "completed": "Molecules Generation Completed",
        "failed": "Molecules are not Generating",
    }

    message = status_map.get(latest["status"], "Unknown status")
    logger.debug("Status check: job=%s status=%s", latest_job_id, latest["status"])

    return {"status": "success", "message": message}
