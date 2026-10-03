# Security and state standard

Read this before working on status changes, roles, permissions, ownership, database writes, RLS, or error responses for protected resources.

## 1. Workflows that change stored state

1. Validate the current stored state inside the transaction.
2. Recheck ownership, assignment or role at mutation time, not only at page load.
3. Lock the authoritative row when concurrent decisions are possible.
4. Write the status, related record and required history atomically.
5. Reject stale, repeated and disallowed transitions without partial writes.
6. Return a deterministic conflict or authorisation response.
7. Test both the successful mutation and the absence of side effects on failure: protected data, status, history and related records stay unchanged.

Status history is separate from detailed business records. For example, a review-decision record may keep a clarification exchange while a status-history record captures only the transition.

## 2. Access control

Hidden buttons are not authorisation. Enforce access in the backend and at the database boundary.

For every protected resource, test:

- missing or expired authentication;
- the permitted role with the correct relationship;
- the permitted role without the relationship (unrelated owner or assignee);
- unrelated roles;
- reassignment between page load and mutation;
- direct access to underlying tables or functions (browser roles must not reach server-only functions);
- information disclosure through error messages or history endpoints.

Return `404` when revealing that another user's resource exists would disclose protected information. Return `403` when the relationship is already established and the caller lacks the capability.

## 3. Test-case labels

Most of these cases are negative (`N`) tests; a story-specific role or visibility rule may be cross-cutting (`X`). Record them in the story matrix with their forbidden side effects, as described in `testing.md`.
