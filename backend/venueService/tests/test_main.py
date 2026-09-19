from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_hello() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "venueService",
        "message": "Hello from venueService",
    }


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "venueService",
        "status": "ok",
    }
