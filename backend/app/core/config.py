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

    # Canonical approved database baseline: ARCH-ST-010.3
    SCHEMA_BASELINE: str = "ARCH-ST-010.3"
    EXPECTED_SCHEMA_SHA256: str = (
        "2187bf7323ba86a203d57c43ad540dcc86ca78adc410ce5554f0a3e4c852cbab"
    )

    # Database file location (defaults strictly to canonical data/operational.db)
    @property
    def DATABASE_PATH(self) -> str:
        return os.getenv("SENTINEL_DB_PATH", str(REPO_ROOT / "data" / "operational.db"))

    # Shipped SQL asset paths
    OPS_SQL_PATH: Path = Field(
        default_factory=lambda: REPO_ROOT / "archive" / "verify-0103" / "ops_0103.sql"
    )
    TRIGS_SQL_PATH: Path = Field(
        default_factory=lambda: REPO_ROOT / "archive" / "verify-0103" / "trigs_0103.sql"
    )

    # CORS origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
