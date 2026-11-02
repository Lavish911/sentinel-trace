from fastapi.testclient import TestClient
from backend.app.core.config import settings


def test_root_endpoint(client: TestClient):
    """Verify that the root endpoint returns service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == settings.PROJECT_NAME
    assert data["schema_baseline"] == "ARCH-ST-010.2"
    assert data["health_endpoint"] == f"{settings.API_V1_STR}/health"


def test_health_check_endpoint(client: TestClient):
    """Verify that GET /api/v1/health returns verified status and schema digest."""
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "HEALTHY"
    assert data["service"] == settings.PROJECT_NAME
    assert data["schema_baseline"] == "ARCH-ST-010.2"
    assert data["schema_verified"] is True
    assert data["table_count"] == 12
    assert data["trigger_count"] == 24
    assert data["schema_digest"] == settings.EXPECTED_SCHEMA_SHA256
