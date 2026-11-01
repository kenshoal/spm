from fastapi import HTTPException, status
from postgrest.exceptions import APIError

NOT_FOUND_ERRCODE = "P0002"
CONFLICT_ERRCODE = "P0004"
TYPE_MISMATCH_ERRCODE = "22023"  # invalid_parameter_value (SCRUM-13 D12)


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


def essential_rpc_error_to_http(exc: APIError) -> HTTPException:
    """Map set_requirement_essential's errcodes (hotfix 25): P0002 unknown requirement,
    P0003 not the assigned coordinator (as a missing one), P0004 closed event, 22023 no note."""
    if exc.code in (NOT_FOUND_ERRCODE, "P0003"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment requirement not found",
        )
    if exc.code == CONFLICT_ERRCODE:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event is closed")
    if exc.code == TYPE_MISMATCH_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A note is required to mark a requirement not essential",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )


def reservation_rpc_error_to_http(exc: APIError) -> HTTPException:
    """Map reserve_equipment's errcodes (SCRUM-13 D6, D12): P0004 is a check
    that failed under the row lock — the pre-check had already passed, so
    the caller sees a conflict, not a server error. 22023 is the type check
    inside the function (migration 0028): the same 422 as the API pre-check.
    P0002 (unknown requirement or equipment) is only reachable in a race
    with a delete."""
    if exc.code == TYPE_MISMATCH_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Equipment type does not match the requirement",
        )
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
