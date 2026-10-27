# Third-party
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.utils.responses import AppError
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.models import ProcessedGpx


async def build(function, *args) -> ProcessedGpx:
    # Runs one of the (blocking) functions of segment_build in a thread; a bad file or bad points answer 422
    try:
        return await run_in_threadpool(function, *args)
    except GpxProcessingError as exc:
        raise AppError(
            422, "Validation failed",
            error_message=exc.user_message,
            error_errors=[{"field": None, "code": exc.code, "message": exc.user_message}],
        )
    except (ValueError, ArithmeticError) as exc:       # a number that the geometry code cannot take (NaN, overflow)
        text = "The geometry could not be processed: it contains values that are not usable."
        raise AppError(422, "Validation failed", error_message=text, error_errors=[{"field": None, "code": "bad_geometry", "message": text}]) from exc
