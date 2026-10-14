from fastapi import HTTPException, status
from postgrest.exceptions import APIError

NOT_FOUND_ERRCODE = "P0002"
CONFLICT_ERRCODE = "P0004"


def rpc_error_to_http(exc: APIError) -> HTTPException:
    if exc.code == NOT_FOUND_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def requirement_rpc_error_to_http(exc: APIError) -> HTTPException:
    """Map transition_equipment_requirement's errcodes (SCRUM-33 D4):
    P0002 unknown id, P0004 disallowed, stale or note-less transition."""
    if exc.code == NOT_FOUND_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment requirement not found",
        )
    if exc.code == CONFLICT_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Transition not allowed"
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def reservation_rpc_error_to_http(exc: APIError) -> HTTPException:
    """Map reserve_equipment's errcodes (SCRUM-13 D6): P0004 is a check
    that failed under the row lock — the pre-check had already passed, so
    the caller sees a conflict, not a server error. P0002 (unknown
    requirement or equipment) is only reachable in a race with a delete."""
    if exc.code == CONFLICT_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Equipment no longer available",
        )
    if exc.code == NOT_FOUND_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment or requirement not found",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )
