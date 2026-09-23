# SCRUM-28 manual API tests (Postman)

`scrum_28.postman_collection.json` holds 39 test cases (TC-01 to TC-39) plus 8 setup requests. Each request has Postman test assertions, so the result shows as pass or fail.

## Before you start

1. Run `docker compose up --build -d auth-service event-request-service` from the repository root. Check that `http://localhost:8001/health` and `http://localhost:8003/health` respond.
2. The collection uses these shared test accounts (password `12345678`, already filled in). See "Test accounts" in `docs/authentication.txt` to create them and assign their roles.

   | Variable prefix | Email | Role |
   | --- | --- | --- |
   | `organiser` | `event_organiser@example.com` | `event_organiser` |
   | `ops` | `event_operations_manager@example.com` | `event_operations_manager` |
   | `coord_a` | `event_coordinator1@example.com` | `event_coordinator` |
   | `coord_b` | `event_coordinator2@example.com` | `event_coordinator` |

3. Import the collection into Postman:
   1. Click **Import** (top left, next to your workspace name), or press **Cmd+O** (Ctrl+O on Windows).
   2. In the import window, click **files** and choose `docs/postman/scrum_28.postman_collection.json`. You can also drag the file anywhere onto the window.
   3. Confirm with **Import**. **SCRUM-28 Track Event Status** appears under **Collections** in the left sidebar.
4. The emails and passwords are pre-filled under the collection's **Variables** tab. Leave the other variables blank; the test scripts fill in tokens, user IDs and request IDs.

## Running

Run the folders **in order**, either one request at a time or with **Run collection**. Later folders depend on IDs saved by earlier ones.

| Folder | Covers |
| --- | --- |
| 0. Setup | Logs in all four accounts and checks each role |
| 1. Organiser submits | Complete submission, validation (422), organiser list |
| 2. Assignment | Only an Ops Manager can assign; assignment alone leaves the request Submitted |
| 3. Discovery and access | `assigned-to-me` scoping, 401/403/404 access matrix |
| 4. Start review | Wrong actors refused (403), completion refused before Confirmed (409), review succeeds once, repeat gives 409 |
| 5. Reassignment and cancellation | Reassigned-away coordinator loses access, current coordinator cancels, terminal-state conflicts |
| 6a. Completion setup | Creates and assigns a second request; prints the SQL to make it Confirmed |
| 6b. Completion | Confirmed → Completed by the assigned coordinator only, then terminal-state conflicts |

**Between 6a and 6b there is one manual step.** No implemented story writes `Confirmed` yet, and the Postman runner cannot pause, so the collection is split around it. Run up to and including folder 6a. Then open the Postman **Console** (bottom left), copy the `UPDATE ... SET status = 'Confirmed'` statement it printed and run it in the Supabase SQL Editor. Finally, run folder 6b on its own (hover over it → **⋯** → **Run**). If the SQL was skipped, TC-34 fails and stops the run instead of letting the later tests fail.

## Notes

- The tests create real rows in the shared Supabase project: two requests named "Postman Charity Run" and "Postman Gala Dinner". Each run adds two more, so ask the team before running them repeatedly on shared dev.
- Access tokens expire (currently no refresh). If requests start returning 401, re-run folder 0.
- A 502 on `/review`, `/cancellation` or `/completion` means migration 0012 is missing from the target database.
