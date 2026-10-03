from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_hello() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "notificationService",
        "message": "Hello from notificationService",
    }


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "notificationService",
        "status": "ok",
    }
