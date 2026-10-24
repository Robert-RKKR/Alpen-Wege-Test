# Standard library
import json
from typing import Any

GENERIC_FAILURE = "The task failed. Please try again or contact support."
TIMEOUT_FAILURE = "The task took too long. Please try again or contact support."
_RESERVED = {"job", "stage", "message"}
_MAX_RESULT_BYTES = 2048


def public_result(retval: dict) -> dict | None:
    # The part of a task result that is stored on the job and shown to the client.
    out = {k: v for k, v in retval.items() if k not in _RESERVED}
    try:
        text = json.dumps(out, default=str)
    except (TypeError, ValueError):
        return None
    if len(text) > _MAX_RESULT_BYTES:
        return {"status": out.get("status")} if "status" in out else None
    return json.loads(text)


def interpret_result(retval: Any) -> tuple[str, dict]:
    # Decide what a returned task result means for the job.
    # Returns: (action, info) with action one of 'keep', 'continue', 'failed', 'succeeded'.
    if not isinstance(retval, dict):
        return "succeeded", {"result": None}
    job = retval.get("job")
    if job == "keep":
        return "keep", {}
    if job == "continue":
        return "continue", {"stage": retval.get("stage")}
    if retval.get("status") == "failed":
        return "failed", {"message": retval.get("message") or GENERIC_FAILURE}
    return "succeeded", {"result": public_result(retval)}
