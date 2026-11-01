"""Hotfix 7 (SCRUM-24 AC3, Q&A #26): the assigned Coordinator reads the queue."""


from registration_support import ATTENDEE_A, ATTENDEE_B, add_event, fill
from test_waitlist_choice_api import COORDINATOR, full_event_with_offer
from waitlist_support import FakeWaitlistRepository, make_waitlist_client


def queue_path(event_id: str) -> str:
    return f"/event-requests/{event_id}/waitlist"


# AC3-H4 (happy, hotfix 7): the queue is listed in order with the offered holder first
def test_the_assigned_coordinator_reads_the_queue_in_order() -> None:
    repo = FakeWaitlistRepository()
    event_id, offered, entries = full_event_with_offer(repo, ATTENDEE_B)

    with make_waitlist_client(
        repo, caller_id=COORDINATOR, roles=("event_coordinator",)
    ) as client:
        response = client.get(queue_path(event_id))

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [offered, entries[ATTENDEE_B]]
    assert [row["status"] for row in response.json()] == ["Offered", "Waiting"]
    assert all(row["attendee_email"].endswith("@example.com") for row in response.json())


# AC3-N4 (negative, hotfix 7): a coordinator who is not assigned is refused, nothing leaks
def test_another_coordinator_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id, _, _ = full_event_with_offer(repo, ATTENDEE_B)

    with make_waitlist_client(
        repo, caller_id="other-coordinator", roles=("event_coordinator",)
    ) as client:
        response = client.get(queue_path(event_id))

    assert response.status_code == 403
    assert "attendee_email" not in response.text


# AC3-N5 (negative, hotfix 7): an attendee cannot read the queue
def test_an_attendee_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=1)
    fill(repo, event_id, 1)

    with make_waitlist_client(repo, caller_id=ATTENDEE_A, roles=("attendee",)) as client:
        response = client.get(queue_path(event_id))

    assert response.status_code == 403


# AC3-B3 (boundary, hotfix 7): an event nobody waits for returns an empty list
def test_an_empty_queue_is_an_empty_list() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=5)
    repo.coordinators[event_id] = COORDINATOR

    with make_waitlist_client(
        repo, caller_id=COORDINATOR, roles=("event_coordinator",)
    ) as client:
        assert client.get(queue_path(event_id)).json() == []


# AC5-H3 (happy, hotfix 5): an attendee's waiting-list entries carry their event's name
def test_my_waitlist_names_the_event() -> None:
    repo = FakeWaitlistRepository()
    event_id, offered, _ = full_event_with_offer(repo, ATTENDEE_B)
    repo.events[event_id]["event_name"] = "Annual Gala"

    with make_waitlist_client(repo, caller_id=ATTENDEE_A, roles=("attendee",)) as client:
        response = client.get("/attendee/waitlist")

    assert response.status_code == 200
    assert [(row["id"], row["event_name"]) for row in response.json()] == [(offered, "Annual Gala")]
