"""Opt-in SCRUM-48 real-API verification; shared test fixtures are retained.

Uses only legitimate development test cards rendered by /auth and normal login.
Never run automatically with pytest: prepare/race require explicit write opt-in.
Credentials and returned tokens remain in memory; reports contain no auth payloads.
"""
import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class VisibleTestPassword(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_cards = False
        self.in_code = False
        self.value = ""

    def handle_starttag(self, tag, attrs):
        if tag == "section" and dict(attrs).get("aria-labelledby") == "test-accounts-heading":
            self.in_cards = True
        if self.in_cards and tag == "code":
            self.in_code = True

    def handle_endtag(self, tag):
        if tag == "code":
            self.in_code = False
        if tag == "section":
            self.in_cards = False

    def handle_data(self, data):
        if self.in_code:
            self.value += data


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Harness:
    def __init__(self, args):
        self.args = args
        for base in (args.auth_url, args.event_url, args.ui_url):
            u = urlparse(base)
            require(u.scheme == "http" and u.hostname in {"127.0.0.1", "localhost", "::1"},
                    "Runtime endpoints must be loopback HTTP")
        self.report_path = Path(args.report)
        self.report = {"date": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
                       "evidence": [], "credential_source": "Existing visible /auth test cards; normal authService login",
                       "limits": ["HTTP barrier does not demonstrate overlapping held database locks",
                                  "Outbox/other storage not exposed by these APIs needs separate read-only MCP corroboration"]}
        self.tokens = {}
        self.identities = {}
        with urlopen(args.ui_url + "/auth", timeout=30) as response:
            parser = VisibleTestPassword()
            parser.feed(response.read().decode())
        require(bool(parser.value), "Public development test cards unavailable; no secret-file fallback")
        self.password = parser.value

    def save(self):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(self.report, indent=2) + "\n")

    def request(self, method, path, role=None, body=None, base=None, invalid=False):
        headers = {"Content-Type": "application/json"}
        if role is not None:
            headers["Authorization"] = "Bearer " + self.tokens[role]
        elif invalid:
            headers["Authorization"] = "Bearer deliberately-invalid-scrum48-test-value"
        req = Request((base or self.args.event_url) + path,
                      data=None if body is None else json.dumps(body).encode(),
                      headers=headers, method=method)
        try:
            with urlopen(req, timeout=45) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        return status, json.loads(raw)

    def login(self, role, email):
        status, body = self.request("POST", "/auth/login", body={"email": email, "password": self.password}, base=self.args.auth_url)
        require(status == 200 and isinstance(body.get("access_token"), str), "Normal login failed for " + role)
        self.tokens[role] = body["access_token"]
        status, me = self.request("GET", "/auth/me", role=role, base=self.args.auth_url)
        require(status == 200 and me.get("email") == email, "Normal auth identity verification failed for " + role)
        self.identities[role] = me
        self.report["identities"] = self.identities

    def snapshot(self, event):
        values = {}
        for label, suffix in (("event", ""), ("history", "/status-history"),
                              ("decisions", "/decisions"), ("assignment", "/coordinator")):
            status, value = self.request("GET", "/event-requests/" + event + suffix, role="owner")
            require(status == 200, "Snapshot " + label + " read failed (HTTP " + str(status) + ")")
            values[label] = value
        return values

    def check_history(self, event, rows, statuses):
        require(len(rows) == len(statuses), "Unexpected history count")
        require([r["new_status"] for r in rows] == statuses, "Unexpected status chain")
        previous = None
        keys = []
        for r in rows:
            require(r["event_request_id"] == event and r["previous_status"] == previous, "Broken event/previous-status chain")
            keys.append((datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")), r["id"]))
            previous = r["new_status"]
        require(keys == sorted(keys), "History is not ordered by absolute instant/id")

    def access(self):
        event = self.args.existing_event
        before = self.snapshot(event)
        self.check_history(event, before["history"], ["Draft", "Submitted", "Under Review"])
        cases = [
            # AC5-P18 (partition): real owner authentication must preserve identical retained evidence.
            ("AC5-P18", "owner", "GET", 200, None),
            # AC5-P19 (partition): current assignment must grant the real coordinator complete history.
            ("AC5-P19", "assigned", "GET", 200, None),
            # AC5-P20 (partition): another real coordinator must not inherit current-assignee access.
            ("AC5-P20", "unassigned", "GET", 404, "HISTORY_NOT_FOUND"),
            # AC5-P21 (partition): venue staff identity must not expose organiser/coordinator history.
            ("AC5-P21", "venue", "GET", 403, "HISTORY_FORBIDDEN"),
            # AC5-P22 (partition): technical support identity must not expose protected history.
            ("AC5-P22", "technical", "GET", 403, "HISTORY_FORBIDDEN"),
            # AC5-N14 (partition): an absent session must not reach retained actor data.
            ("AC5-N14", None, "GET", 401, None),
            # AC5-N15 (partition): a present invalid credential must not grant history access.
            ("AC5-N15", "invalid", "GET", 401, None),
            # AC5-N16 (partition): legitimate owner authentication must not expose a history-write API.
            ("AC5-N16", "owner", "POST", 405, None),
        ]
        for case_id, role, method, expected, code in cases:
            # AC5: distinguish real actor/relationship partitions without leaking rows.
            status, value = self.request(method, "/event-requests/" + event + "/status-history",
                                         role=None if role == "invalid" else role,
                                         invalid=role == "invalid", body={} if method == "POST" else None)
            self.report["evidence"].append({"case_id": case_id, "actor": role or "unauthenticated", "method": method,
                                            "status": status, "body": value})
            self.save()
            require(status == expected, "Unexpected HTTP status in access partition " + str(role))
            if expected == 200:
                require(value == before["history"], "Authorised history body differs")
            else:
                require(isinstance(value, dict) and "detail" in value, "Denied request exposed history body")
                if code:
                    require(value["detail"] == {"code": code, "message": "Status history is not accessible"}, "Wrong privacy denial body")
            require(self.snapshot(event) == before, "Denied/read request changed full authorised API snapshot")
        self.report["event_id"] = event
        self.report["before"] = self.report["after"] = before

    def prepare(self):
        require(self.args.allow_shared_test_write, "Explicit shared test write opt-in required")
        require(not Path(self.args.fixture).exists(), "Fixture record already exists; refuse duplicate shared creation")
        payload = {"event_name": "SCRUM-48 real API overlap check - " + datetime.now(timezone.utc).isoformat(),
                   "purpose": "Verify real access and duplicate review recording", "description": "Retained test-only shared fixture. Two legitimate coordinator review requests compete.",
                   "proposed_date_times": ["2026-11-20T02:00:00Z"], "expected_attendance": 25,
                   "venue_requirements": "Seminar room for 25 participants", "accessibility_needs": "Step-free access",
                   "equipment_requirements": "No technical kit required", "registration_needs": "No registration required"}
        status, created = self.request("POST", "/event-requests/submissions", role="owner", body=payload)
        self.report["creation"] = {"status": status, "body": created}
        self.save()
        require(status == 201, "Shared fixture creation did not return 201; no retry")
        event = created["id"]
        record = {"event_id": event, "created": created, "payload": payload, "retained": True}
        Path(self.args.fixture).write_text(json.dumps(record, indent=2) + "\n")
        self.report["event_id"] = event
        require(created["status"] == "Submitted", "Fixture is not Submitted")
        status, assignment = self.request("POST", "/event-requests/" + event + "/coordinator", role="manager",
                                          body={"coordinator_id": self.identities["assigned"]["id"]})
        self.report["assignment"] = {"status": status, "body": assignment}
        self.save()
        require(status == 201, "Real assignment did not return 201; retained fixture needs manual assessment")
        before = self.snapshot(event)
        self.check_history(event, before["history"], ["Submitted"])
        require(before["history"][0]["actor_id"] == self.identities["owner"]["id"] and
                before["history"][0]["actor_role"] == "event_organiser" and
                before["history"][0]["source"] == "event_request.created" and
                before["history"][0]["entry_kind"] == "created", "Creation metadata incorrect")
        self.report["before"] = before
        record["before"] = before
        Path(self.args.fixture).write_text(json.dumps(record, indent=2) + "\n")

    def race(self):
        require(self.args.allow_shared_test_write, "Explicit shared test write opt-in required")
        record = json.loads(Path(self.args.fixture).read_text())
        require("race_attempted" not in record, "Race already attempted; refuse a second shared run")
        event = record["event_id"]
        before = self.snapshot(event)
        require(before["event"]["event_name"].startswith("SCRUM-48 real API overlap check - "),
                "Fixture lacks the known SCRUM-48 test-only name prefix")
        require(before["event"]["organiser_id"] == self.identities["owner"]["id"] and
                before["assignment"]["coordinator_id"] == self.identities["assigned"]["id"],
                "Fixture owner or current coordinator differs from legitimate test actors")
        require(before == record["before"] and before["event"]["status"] == "Submitted", "Fixture changed before competition")
        record["race_attempted"] = datetime.now(timezone.utc).isoformat()
        Path(self.args.fixture).write_text(json.dumps(record, indent=2) + "\n")
        barrier = threading.Barrier(2)
        def compete(index):
            barrier.wait(timeout=10)
            start = time.monotonic_ns()
            status, value = self.request("POST", "/event-requests/" + event + "/review", role="assigned", body={})
            return {"request": index, "start_ns": start, "end_ns": time.monotonic_ns(), "status": status, "body": value}
        # AC1-X3 (cross-cutting): competing real calls must record one transition without duplicate evidence.
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(compete, i) for i in range(2)]
            outcomes = [j.result() for j in jobs]
        after = self.snapshot(event)
        self.report.update({"event_id": event, "before": before, "outcomes": outcomes, "after": after})
        self.save()
        require(max(o["start_ns"] for o in outcomes) < min(o["end_ns"] for o in outcomes),
                "Client HTTP intervals did not overlap; concurrency evidence is inconclusive")
        require(sorted(o["status"] for o in outcomes) == [200, 409], "Expected one 200 and one 409 from duplicate review competition")
        conflict = "Cannot move event request " + event + " to Under Review from its current status"
        require(next(o["body"] for o in outcomes if o["status"] == 409) == {"detail": conflict}, "Wrong real transition conflict response")
        self.check_history(event, after["history"], ["Submitted", "Under Review"])
        require(after["history"][:-1] == before["history"], "Existing creation history changed")
        latest = after["history"][-1]
        require(latest["actor_id"] == self.identities["assigned"]["id"] and latest["actor_role"] == "event_coordinator" and latest["source"] == "coordinator.review" and latest["entry_kind"] == "transition", "Review attribution incorrect")
        require(after["event"]["status"] == latest["new_status"] == "Under Review", "Latest/current mismatch")
        for key in before["event"]:
            if key not in {"status", "updated_at"}:
                require(after["event"][key] == before["event"][key], "Competing review changed unrelated event field")
        require(after["decisions"] == before["decisions"] == [] and after["assignment"] == before["assignment"], "Unexpected decision/assignment effects")
        status, rows = self.request("GET", "/event-requests/" + event + "/status-history", role="assigned")
        require(status == 200 and rows == after["history"], "Real coordinator and owner history differ")
        # AC3-N4 (negative): a real serial retry must preserve the complete successful snapshot.
        status, repeated = self.request("POST", "/event-requests/" + event + "/review", role="assigned", body={})
        self.report["serial_repeat"] = {"status": status, "body": repeated}
        self.save()
        require(status == 409 and repeated == {"detail": conflict}, "Serial repeat did not refuse exactly")
        require(self.snapshot(event) == after, "Serial refusal changed complete API snapshot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["access", "prepare", "race"])
    parser.add_argument("--auth-url", default="http://127.0.0.1:8001")
    parser.add_argument("--event-url", default="http://127.0.0.1:8003")
    parser.add_argument("--ui-url", default="http://127.0.0.1:3000")
    parser.add_argument("--existing-event", default="f64b2d81-a825-49e3-b792-fca51b23b75d")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--allow-shared-test-write", action="store_true")
    args = parser.parse_args()
    h = None
    try:
        h = Harness(args)
        accounts = [("owner", "event_organiser@example.com"), ("assigned", "event_coordinator2@example.com")]
        if args.mode == "access":
            accounts += [("unassigned", "event_coordinator1@example.com"), ("venue", "venue_staff@example.com"), ("technical", "technical_support@example.com")]
        if args.mode == "prepare":
            accounts += [("manager", "event_operations_manager@example.com")]
        for role, email in accounts:
            h.login(role, email)
        getattr(h, args.mode)()
        h.report["result"] = "PASS"
        h.save()
        print(json.dumps({"result": "PASS", "mode": args.mode, "event_id": h.report.get("event_id"), "report": str(h.report_path)}))
    except (AssertionError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        # Never dump requests, headers, raw Auth responses or credential values.
        message = str(error) if isinstance(error, AssertionError) else type(error).__name__
        if h is not None:
            h.report.update({"result": "FAIL", "failure": message})
            h.save()
        print(json.dumps({"result": "FAIL", "mode": args.mode, "failure": message}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
