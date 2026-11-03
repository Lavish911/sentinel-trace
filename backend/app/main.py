from contextlib import asynccontextmanager
import logging
import sqlite3
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
COCKPIT_HTML_PATH = TEMPLATES_DIR / "cockpit.html"

from backend.app.core.config import settings
from backend.app.api.v1.api import api_router
from backend.app.db.session import create_connection
from backend.app.db.init_db import verify_schema, initialize_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel_trace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup checks and graceful shutdown."""
    logger.info("Initializing %s (Baseline: %s)", settings.PROJECT_NAME, settings.SCHEMA_BASELINE)

    # 1. Enforce database presence and prevent accidental empty file creation
    db_path = Path(settings.DATABASE_PATH)
    if settings.DATABASE_PATH != ":memory:":
        if not db_path.is_file():
            raise RuntimeError(
                f"Canonical ARCH-ST-010.3 operational database not found at '{db_path}'. "
                "Normal FastAPI startup does not create, initialize, or seed databases. "
                "Please run explicit dataset generation: python scripts/generate_dataset.py"
            )
        if db_path.stat().st_size == 0:
            raise RuntimeError(
                f"Canonical database at '{db_path}' is an empty 0-byte file. "
                "Please run explicit dataset generation: python scripts/generate_dataset.py"
            )

    conn = create_connection()
    try:
        schema_info = verify_schema(conn)
        if not schema_info["verified"]:
            raise RuntimeError(
                f"Database schema verification failed for '{settings.DATABASE_PATH}'. "
                f"Expected {schema_info['expected_table_count']} tables, {schema_info['expected_trigger_count']} triggers, "
                f"digest {schema_info['expected_schema_digest']}. "
                f"Observed {schema_info['table_count']} tables, {schema_info['trigger_count']} triggers, "
                f"digest {schema_info['schema_digest']}. "
                "Normal startup does not alter or re-initialize databases. "
                "Please run explicit setup: python scripts/generate_dataset.py"
            )

        # 2. Enforce that database is fully seeded with claims records
        claims_count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        if claims_count == 0:
            raise RuntimeError(
                f"Database at '{settings.DATABASE_PATH}' has schema but 0 claims (unseeded). "
                "Normal startup does not seed records. "
                "Please run explicit dataset generation: python scripts/generate_dataset.py"
            )

        logger.info(
            "Schema verification status: PASS (Tables: %d/12, Triggers: %d/27, Claims: %d, Digest: %s...)",
            schema_info["table_count"],
            schema_info["trigger_count"],
            claims_count,
            str(schema_info["schema_digest"])[:16],
        )
    finally:
        conn.close()

    yield
    logger.info("Shutting down %s", settings.PROJECT_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(sqlite3.IntegrityError)
async def sqlite_integrity_error_handler(request: Request, exc: sqlite3.IntegrityError):
    """Convert SQLite trigger aborts and constraint violations into structured JSON responses."""
    error_message = str(exc)
    return JSONResponse(
        status_code=400,
        content={
            "error_type": "DATABASE_INTEGRITY_VIOLATION",
            "message": error_message,
            "path": request.url.path,
        },
    )


@app.get("/")
def root(request: Request):
    """Root endpoint: serves interactive forensic cockpit for browsers or JSON metadata for API clients."""
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header and COCKPIT_HTML_PATH.exists():
        return HTMLResponse(content=COCKPIT_HTML_PATH.read_text(encoding="utf-8"))
    return {
        "service": settings.PROJECT_NAME,
        "description": settings.PROJECT_DESCRIPTION,
        "version": settings.VERSION,
        "schema_baseline": settings.SCHEMA_BASELINE,
        "cockpit_url": "/cockpit",
        "docs_url": "/docs",
        "health_endpoint": f"{settings.API_V1_STR}/health",
    }


@app.get("/cockpit", response_class=HTMLResponse)
def cockpit():
    """Direct URL for the forensic investigator cockpit."""
    if COCKPIT_HTML_PATH.exists():
        return HTMLResponse(content=COCKPIT_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Cockpit template not found</h1>", status_code=404)
