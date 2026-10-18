"""Registration persistence (SCRUM-21). Stub: the real repository follows the Red tests."""

from app.repositories.event_request_repository import SupabaseRepositoryError


class RegistrationRpcError(SupabaseRepositoryError):
    """`register_for_event` refused the call.

    errcode is the Postgres ERRCODE (P0002 event not found, P0004 refused) and
    reason the function's message ('registration not open', 'already registered',
    'event full'), so callers never parse prose written for people.
    """

    def __init__(
        self, message: str, errcode: str | None = None, reason: str | None = None
    ) -> None:
        super().__init__(message)
        self.errcode = errcode
        self.reason = reason
