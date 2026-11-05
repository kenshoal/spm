"""SCRUM-38 AC1 and AC2 (hotfix 2, H5): who is told when a registration is saved.

The database decides atomically whether a save took the event from below capacity to
full (Registered plus Offered places, under the event lock) and returns that as
`filled_event`; database/verify_release_1_hotfixes_2.sql proves the decision. These
tests prove the service acts on it: the full notice follows the flag, not a recount.
"""

from typing import Any

from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NOW,
    FakeRegistrationRepository,
    add_event,
    fill,
)
from test_registration_notification import (
    COORDINATOR,
    SpyNotificationClient,
    full_event,
    recipients,
    register_path,
    spy_client,
)
from waitlist_support import (
    FakeWaitlistRepository,
    add_offer,
    make_waitlist_client,
)

from app.services.registration_service import RegistrationService
from app.services.waitlist_service import WaitlistService


# AC2-H2 (happy): a pending offer holds a place, so the registration that takes the last
# free place announces "full" even though Registered rows alone are below capacity
def test_a_pending_offer_counts_towards_full() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=3)
    repo.coordinators[event_id] = COORDINATOR
    fill(repo, event_id, 1)
    add_offer(repo, event_id, ATTENDEE_B)  # 1 Registered + 1 Offered = 2 of 3
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.registration_service = RegistrationService(repo, repo, notification_client=spy)
    with client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert recipients(spy) == sorted(["organiser-1", COORDINATOR])


# AC2-N1 (negative): the service does not recount. A save the database did not mark as
# filling the event sends no full notice, whatever the count looks like afterwards
def test_a_save_that_did_not_fill_the_event_announces_nothing() -> None:
    class NotFilling(FakeRegistrationRepository):
        def register(self, event_id: str, attendee_id: str, now: Any) -> dict[str, Any]:
            return {**super().register(event_id, attendee_id, now), "filled_event": False}

    repo = NotFilling()
    event_id = full_event(repo, registered=9)  # this registration reaches capacity
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert spy.full == []
    assert [c["attendee_id"] for c in spy.confirmed] == [ATTENDEE_A]


# AC2-N2 (negative): the manual path follows the flag too. A Coordinator registration the
# database did not mark as filling the event (the VIP case: it was already full) announces nothing
def test_a_manual_save_that_did_not_fill_the_event_announces_nothing() -> None:
    from test_registration_notification import manual_setup

    client, repo, event_id, spy, _, email = manual_setup(registration_capacity=3)
    fill(repo, event_id, 2)  # this registration reaches capacity
    original = repo.coordinator_register
    repo.coordinator_register = lambda *a, **k: {**original(*a, **k), "filled_event": False}  # type: ignore[method-assign]

    with client:
        response = client.post(
            f"/event-requests/{event_id}/registrations", json={"attendee_email": email}
        )

    assert response.status_code == 201
    assert spy.full == []
    assert len(spy.confirmed) == 1


# AC1-H1 (happy): accepting an offered place confirms the registration to the Attendee, once
def test_accepting_an_offer_sends_the_confirmation() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.waitlist_service = WaitlistService(repo, notification_client=spy)
    with client:
        response = client.post(f"/attendee/waitlist/{entry_id}/acceptance")

    assert response.status_code == 200
    [registration] = [r for r in repo.registrations if r["attendee_id"] == ATTENDEE_A]
    assert spy.confirmed == [
        {
            "event_request_id": event_id,
            "attendee_id": ATTENDEE_A,
            "event_name": "Community Dinner",
            "registration_id": registration["id"],
        }
    ]


# AC2-N3 (negative): accepting a held offer must not announce "full" again, even when the
# event is full afterwards
def test_accepting_an_offer_does_not_announce_full() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    repo.coordinators[event_id] = COORDINATOR
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)  # 1 Registered + 1 Offered = full already
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.waitlist_service = WaitlistService(repo, notification_client=spy)
    with client:
        client.post(f"/attendee/waitlist/{entry_id}/acceptance")

    assert spy.full == []


# AC1-N1 (negative): a refused acceptance (expired offer) confirms nothing
def test_a_refused_acceptance_sends_no_confirmation() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.waitlist_service = WaitlistService(repo, notification_client=spy)
    client.app.dependency_overrides.clear()
    from app.clock import get_now
    from app.controllers import event_request_controller

    client.app.dependency_overrides[event_request_controller.get_authenticated_caller] = (
        lambda: event_request_controller.AuthenticatedCaller(id=ATTENDEE_A, roles=("attendee",))
    )
    client.app.dependency_overrides[get_now] = lambda: NOW.replace(year=NOW.year + 5)
    with client:
        response = client.post(f"/attendee/waitlist/{entry_id}/acceptance")

    assert response.status_code == 409
    assert spy.confirmed == []


# AC1-N2 (negative): if the registration cannot be read back after an accepted offer, the
# acceptance still stands (200) and nothing is sent, because there is nothing to name
def test_acceptance_survives_a_registration_that_cannot_be_found() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)
    repo.list_for_attendee = lambda attendee_id: []  # type: ignore[method-assign]
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.waitlist_service = WaitlistService(repo, notification_client=spy)
    with client:
        response = client.post(f"/attendee/waitlist/{entry_id}/acceptance")

    assert response.status_code == 200
    assert response.json()["registration"] is None
    assert spy.confirmed == []


# AC1-N3 (negative): if the event cannot be read for its name, the confirmation is still sent
def test_confirmation_survives_a_failed_event_lookup() -> None:
    from app.repositories import SupabaseRepositoryError

    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    def fail(event_id: str) -> None:
        raise SupabaseRepositoryError("down")

    repo.get_event = fail  # type: ignore[method-assign]
    spy = SpyNotificationClient()

    client = make_waitlist_client(repo, caller_id=ATTENDEE_A)
    client.app.state.waitlist_service = WaitlistService(repo, notification_client=spy)
    with client:
        response = client.post(f"/attendee/waitlist/{entry_id}/acceptance")

    assert response.status_code == 200
    assert [c["event_name"] for c in spy.confirmed] == [None]
