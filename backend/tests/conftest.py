import os
import sys
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

# Ensure backend package is in python search path
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.config import settings
from backend.app.db.session import create_connection, get_db
from backend.app.db.init_db import initialize_database
from backend.app.main import app


@pytest.fixture
def in_memory_db() -> Generator:
    """Fixture providing an in-memory SQLite database initialized with ARCH-ST-010.3 schema."""
    conn = create_connection(":memory:")
    initialize_database(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def client(in_memory_db) -> Generator[TestClient, None, None]:
    """Test client with database dependency overridden to the in-memory test database."""
    def override_get_db():
        yield in_memory_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

