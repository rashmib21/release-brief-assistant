import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from .config import get_settings
from .db import Base, add_missing_columns, engine
from .logging_config import log_event, request_id_var, setup_logging
from .routers import releases, statements, versions

BUILD = "2026-10-16b"  # shown in the page footer so you can tell which version is really running
settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("app")


def init_database(attempts: int = 6, wait_seconds: float = 5.0) -> None:
    """Create tables. A hosted Postgres (Neon) can be asleep for a few seconds on a cold start,
    so retry instead of crashing the container on the first refused connection."""
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            add_missing_columns()
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.warning("database not ready (attempt %s of %s), retrying in %.0fs", attempt, attempts, wait_seconds)
            time.sleep(wait_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    log_event(logger, "startup", llm_provider=settings.llm_provider, model=settings.gemini_model)
    yield


app = FastAPI(title="Release Brief Assistant", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except IntegrityError:
        # Two requests changed the same thing at once (double click, two tabs). Not a server fault.
        logger.warning("conflicting write on %s %s", request.method, request.url.path, exc_info=True)
        response = JSONResponse(
            {"detail": {"message": "Someone else changed this at the same moment. Reload and try again.", "request_id": rid, "retryable": True}},
            status_code=409,
        )
    except (OperationalError, DBAPIError):
        # Hosted Postgres can be asleep or restarting for a moment. Say so, so the person retries instead of giving up.
        logger.exception("database error on %s %s", request.method, request.url.path)
        response = JSONResponse(
            {"detail": {"message": "The database is not reachable right now. Wait a few seconds and retry.", "request_id": rid, "retryable": True}},
            status_code=503,
        )
    except Exception:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        response = JSONResponse(
            {"detail": {"message": "Unexpected server error. Please retry; if it keeps happening, quote the reference below.", "request_id": rid}},
            status_code=500,
        )
    response.headers["x-request-id"] = rid
    if request.url.path.startswith("/api"):
        log_event(
            logger,
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    request_id_var.reset(token)
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": settings.llm_provider, "build": BUILD}


app.include_router(releases.router)
app.include_router(versions.router)
app.include_router(statements.router)

# Serve the built React app from the same service (no CORS needed).
dist = Path(settings.frontend_dist)
if not dist.is_absolute():
    dist = (Path(__file__).resolve().parent.parent / dist).resolve()

if (dist / "index.html").exists():
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        if full_path:
            candidate = (dist / full_path).resolve()
            # Only serve files that really live inside the dist folder (blocks ../ tricks).
            if candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
        return FileResponse(dist / "index.html")
