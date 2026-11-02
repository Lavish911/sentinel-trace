import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field

# Base repository root (sentinel-trace)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseModel):
    """Central configuration for SENTINEL//TRACE backend."""

    PROJECT_NAME: str = "SENTINEL//TRACE"
    PROJECT_DESCRIPTION: str = (
        "Forensic Insurance Fraud Network Intelligence & SIU Platform"
    )
    API_V1_STR: str = "/api/v1"
    VERSION: str = "0.1.0"

    # Provisional approved database baseline: ARCH-ST-010.2
    SCHEMA_BASELINE: str = "ARCH-ST-010.2"
    EXPECTED_SCHEMA_SHA256: str = (
        "26e2218f1c6541f2eabf9f4549f6c943c17b158588648cddf90919f21f11479a"
    )

    # Database file location (defaults to local SQLite file)
    DATABASE_PATH: str = Field(
        default_factory=lambda: os.getenv(
            "SENTINEL_DB_PATH", str(REPO_ROOT / "sentinel_trace.db")
        )
    )

    # Shipped SQL asset paths
    OPS_SQL_PATH: Path = Field(
        default_factory=lambda: REPO_ROOT / "archive" / "verify-0102" / "ops_0102.sql"
    )
    TRIGS_SQL_PATH: Path = Field(
        default_factory=lambda: REPO_ROOT / "archive" / "verify-0102" / "trigs_0102.sql"
    )

    # CORS origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
