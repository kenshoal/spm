"""Opt-in real PostgREST equivalent of AC5-B7; no new logical case/Auth proof.

Load the companion disposable fixture and the exact migration0035 first.
Use --base-url for the loopback PostgREST root, with db-max-rows=3.
"""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import httpx


# AC5-B7 (boundary): real capped RPC HTTP must retain all evidence and leave storage unchanged.
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--repo", default=str(Path(__file__).resolve().parents[3]))
    a = p.parse_args()
    assert urlparse(a.base_url).hostname in {"127.0.0.1", "localhost"}, (
        "Loopback disposable PostgREST only"
    )
    service = Path(a.repo).resolve() / "backend/eventRequestService"
    sys.path[:0] = [str(service), str(service / "tests")]
    import app
    from app.repositories import SupabaseEventRequestRepository
    from test_arrangement_reviews import EVENT, normalized, review

    assert Path(app.__file__).resolve().is_relative_to(service)

    def storage_snapshot():
        rows = []
        cursor = None
        with httpx.Client(base_url=a.base_url) as client:
            while True:
                params = {"select": "*", "order": "id.asc", "limit": "1000"}
                if cursor:
                    params["id"] = f"gt.{cursor}"
                response = client.get("/arrangement_reviews", params=params)
                response.raise_for_status()
                page = response.json()
                if not page:
                    return rows
                rows.extend(page)
                cursor = page[-1]["id"]

    before = storage_snapshot()
    assert len(before) == 11, "Require all seven reviews and four excluded controls"
    expected = [
        review(n, arrangement="venue_booking" if n % 2 else "equipment_reservation")
        for n in range(7, 0, -1)
    ]
    expected[-1]["raised_at"] = "2026-10-14T00:00:00Z"
    repository = SupabaseEventRequestRepository(
        a.base_url, "sb_secret_disposable_fixture"
    )
    # Direct PostgREST lacks Supabase's /rest/v1 mount; only the test mount changes.
    repository._client.base_url = a.base_url
    requests = []
    repository._client.event_hooks = {
        "request": [
            lambda r: requests.append(
                (r.method, r.url.path, dict(r.url.params), r.content.decode())
            )
        ]
    }
    try:
        actual = repository.list_arrangement_reviews(EVENT)
    finally:
        repository.close()
    assert normalized(actual) == normalized(expected), (len(actual), actual)
    assert len(requests) == 4, requests
    assert all(
        method == "POST" and path == "/rpc/get_outstanding_arrangement_reviews"
        for method, path, _, _ in requests
    )
    assert all(
        json.loads(body) == {"p_event_request_id": EVENT} for _, _, _, body in requests
    )
    assert all(
        params["order"] == "raised_at.desc,id.desc" for _, _, params, _ in requests
    )
    assert storage_snapshot() == deepcopy(before), (
        "Read must not change any persisted fixture field"
    )
    print(
        "AC5-B7 real PostgREST PASS: exact7 full mixed-domain records; tie/older ordering; cleared/other-event controls excluded;4 RPC POST pages at cap3; full11-row storage snapshot unchanged."
    )


if __name__ == "__main__":
    main()
