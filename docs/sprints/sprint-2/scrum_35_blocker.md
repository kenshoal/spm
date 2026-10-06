# Sprint 2 — SCRUM-35 blocker (IMP-S2-01)

**Recorded:** 6 October 2026, Singapore time.  
**State:** Active. SCRUM-35 remains In Progress in Sprint 2; its original Jira story and six criteria are unchanged. Any return to the backlog after Sprint Review is reserved for the user.  
**Record type:** Verified implementation boundary and requester-approved plan; not minutes of a team meeting or a Product Owner scope decision.

## Requester-approved current delivery boundary

- The owning organiser creates one Pending change request for an Approved or Planning event.
- The owning organiser and current assigned coordinator can view retained proposals.
- The active event plan remains unchanged, and no change-triggered arrangement flags or notifications are created.
- Approval/rejection buttons are unavailable. The decision API checks the current assignment and amendment, then returns HTTP 409 with `detail.code = CHANGE_DECISIONS_UNAVAILABLE` without invoking the decision primitive.
- Existing decision records, database functions and migrations are retained for later integration; their presence is not evidence of an enabled public decision workflow.

The requester approved this boundary in the current conversation before implementation. It does not narrow the original Jira criteria, establish full story completion, change the Sprint Goal, or record PO/team approval.

## Impediment and impact

The decision primitive previously applied proposed values immediately. Venue, equipment and registration arrangements were not revalidated alongside that change, so an approved amendment could make the current plan inconsistent with committed arrangements. A staff alert alone would not establish whether the proposed change is feasible.

The interim create/view workflow keeps proposals Pending while these dependencies are resolved. The original broader after-submission criterion is only partially covered by Approved/Planning eligibility. Original Jira AC2 still needs approval/rejection, AC3 needs arrangement flags, AC4 needs conflict resolution/confirmation guards, AC5 needs integrated arrangement-preservation proof, and AC6 needs organiser outcome notifications. Therefore SCRUM-35 is **not Done** and its partial implementation does not count as a completed story or Done Increment.

| Dependency | Existing related work | What still needs agreement |
| --- | --- | --- |
| Resource impact and persistent review records | SCRUM-49 covers equipment reschedule/unavailability review; venue/registration coverage is incomplete. | Which changed fields affect which arrangements, where assessment is stored, and who owns each integration. |
| Conflicts and confirmation | SCRUM-20 covers venue conflicts. | Complete venue/equipment confirmation guard and how proposed availability is protected until application. |
| Outcome notification | SCRUM-36 | Explicit change approval/rejection producer contract and ownership. |
| Arrangement alerts | SCRUM-37 AC4 | Saved flag trigger and current staff recipients; historic creator/decider does not establish current responsibility. |

The teammate-proposed alert contract is retained: `arrangement_needs_review`, payload `event_request_id`, `change_request_id`, `arrangement` (`venue_booking` or `equipment_reservation`) and `arrangement_id`; `event_id = str(uuid5(NAMESPACE_URL, f"needs-review:{change_request_id}:{arrangement_id}"))`. Send after the durable flag is saved. This increment sends none; use before final approval would require agreement on the trigger semantics because current Jira describes approved changes.

## Proposed follow-up flow — not implemented or agreed by the team

Organiser proposes → coordinator identifies affected arrangements → relevant staff assess the proposal → coordinator gives the final decision → event and arrangements are updated consistently → responsible users are notified.

Staff need the current arrangement, proposed differences and relevant requirements. Their assessment must refer to the actual proposal being decided; changed or expired availability must not be treated as guaranteed approval. Resource services own their booking/reservation rules. This proposal changes the current Jira order of flagging after approval, so discuss it with the PO/team rather than silently rewriting criteria or notification contracts.

## Next actions and ownership

1. Raise IMP-S2-01 at the actual Daily Scrum, inspect its effect on the Sprint Goal and agree an actionable next-day plan.
2. PO/team clarify approval order and the broad lifecycle requirement; Developers agree assessment records, resource owners and notification hand-offs; the Scrum Master helps remove the impediment. Specific people and deadlines are pending agreement.
3. Record the actual discussion, Jira decisions and ownership links here. Do not invent meeting attendance, PO approval, resolved status or next-sprint commitments.
4. Resume final decisions only after the relevant feasibility, application and notification boundaries are implemented and tested.

## Evidence and verification limits

- [Original Jira story](https://is212g9t4.atlassian.net/browse/SCRUM-35).
- [Existing PR #43](https://github.com/jarenlimhaan/spm/pull/43); this is a partial-story PR, not closure of SCRUM-35.
- [Current test specification and execution records](../../testcases/scrum_35_testcases.md).
- `backend/eventRequestService/app/controllers/event_request_controller.py`: public create/view routes and deferred-decision response.
- `frontend/app/coordination/requests/[id]/change-request-panel.tsx`: read-only proposal view.
- `database/verify_pending_event_change_requests.sql`: rolled-back create/Pending/duplicate/privilege verification, separate from API and mocked browser proof.
- Google Docs mirror: [spm project](https://docs.google.com/document/d/1V7orgZ1LCibmJhfFt_ZDzqhZnoy3mvZzpJi76_7IiH8/edit), Sprint 2 Planning → SCRUM-35 blocker.

Fresh test counts and environment limitations are recorded in the test document. Human review and full original-story completion remain outstanding even if this partial PR's automated checks pass.

## Scrum-practice sources

- **2020 Scrum Guide**, PDF p. 10 (Daily Scrum): inspect progress toward the Sprint Goal and adapt the next day's plan; pp. 12–13: transparent Sprint Backlog, usable integrated work and Definition of Done. Incomplete items cannot be claimed as Done Increments. Scope decisions involving the PO are separate from this requester-approved implementation boundary.
- **Scrum Primer v2.0**, PDF p. 11 (Daily Scrum): surface obstacles and coordinate follow-up; p. 13 (Product Backlog Refinement): analyse, split and refine work. The 2020 Guide takes precedence where the older Primer differs.
- User-supplied local sources: `SPM/SCRUM guide/2020-Scrum-Guide-US.pdf` and `SPM/SCRUM guide/scrumprimer20.pdf`. Their formal grading-rubric status has not been verified.

## DSU draft — preparation, not confirmed minutes

**What I did today**

Aligned SCRUM-35 to a create-and-view increment, blocked approval/rejection in the API and UI, and documented the current tests and remaining dependencies while retaining the original Jira criteria.

**What I will do tomorrow**

Review the partial PR and agree with the team how venue and technical staff assess proposed changes before final coordinator decisions, including assessment ownership and notification recipients.

**Blockers:**

IMP-S2-01 is active: arrangement revalidation, confirmation guards and change-notification hand-offs are not integrated. Requests remain Pending; SCRUM-35 stays In Progress until Sprint Review, and this partial work is not full story completion.
