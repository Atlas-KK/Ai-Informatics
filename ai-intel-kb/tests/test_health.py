from fastapi.testclient import TestClient

from ai_intel.api.app import create_app
from ai_intel.config import Settings


def test_health_check_starts_with_an_empty_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "storage": "ready",
        "phase": "phase7",
    }
