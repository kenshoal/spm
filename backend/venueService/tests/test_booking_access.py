from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)


def test_venue_staff_can_list_booking_requests() -> None:
    response = client.get("/venue-booking-requests")

    assert response.status_code == 200
    assert response.json() == []


def test_booking_requests_require_authentication() -> None:
    app.dependency_overrides.clear()

    response = client.get("/venue-booking-requests")

    assert response.status_code == 401


def test_booking_requests_are_forbidden_for_unrelated_roles() -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000002",
        roles=("attendee",),
    )
    app.dependency_overrides.pop(require_venue_staff, None)

    response = client.get("/venue-booking-requests")

    assert response.status_code == 403
