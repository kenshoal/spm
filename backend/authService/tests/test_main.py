from fastapi.testclient import TestClient


def test_hello(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "authService",
        "message": "Hello from authService",
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "authService",
        "status": "ok",
    }
