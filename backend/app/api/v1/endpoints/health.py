from datetime import datetime, timezone
import sqlite3
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.db.init_db import verify_schema


router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp_utc: str
    schema_baseline: str
    schema_verified: bool
    schema_digest: str
    table_count: int
    trigger_count: int
    details: Optional[str] = None


@router.get("/health", response_model=HealthResponse)
def health_check(db: sqlite3.Connection = Depends(get_db)) -> HealthResponse:
    """System health check and cryptographic schema verification endpoint."""
    schema_info = verify_schema(db)
    is_verified = bool(schema_info["verified"])

    status_str = "HEALTHY" if is_verified else "SCHEMA_UNINITIALIZED_OR_MISMATCH"
    details_str = (
        "Canonical ARCH-ST-010.3 schema verified and compliant."
        if is_verified
        else f"Tables: {schema_info['table_count']}/12, Triggers: {schema_info['trigger_count']}/27."
    )

    return HealthResponse(
        status=status_str,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        schema_baseline=settings.SCHEMA_BASELINE,
        schema_verified=is_verified,
        schema_digest=str(schema_info["schema_digest"]),
        table_count=int(schema_info["table_count"]),
        trigger_count=int(schema_info["trigger_count"]),
        details=details_str,
    )
