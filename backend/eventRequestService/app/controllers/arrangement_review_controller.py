"""Domain staff review queues and exact-review clearing; no event ticket access."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.controllers.event_request_controller import CallerDependency, ServiceDependency
from app.models.arrangement_review import ArrangementReviewResponse
from app.services.event_request_service import ArrangementReviewActionError

router = APIRouter(prefix="/arrangement-reviews", tags=["arrangement reviews"])
DOMAIN_ROLES = {
    "venue_booking": "venue_staff",
    "equipment_reservation": "technical_support",
}


def _forbidden() -> HTTPException:
    return HTTPException(
        403,
        detail={
            "code": "ARRANGEMENT_REVIEW_FORBIDDEN",
            "message": "Arrangement review is not accessible",
        },
    )


@router.get("", response_model=list[ArrangementReviewResponse])
def list_domain_reviews(
    arrangement: Literal["venue_booking", "equipment_reservation"],
    caller: CallerDependency,
    service: ServiceDependency,
) -> list[ArrangementReviewResponse]:
    if DOMAIN_ROLES[arrangement] not in caller.roles:
        raise _forbidden()
    return service.list_arrangement_reviews_for_arrangement(arrangement)


@router.post("/{review_id}/clear", response_model=ArrangementReviewResponse)
def clear_review(
    review_id: UUID,
    caller: CallerDependency,
    service: ServiceDependency,
) -> ArrangementReviewResponse:
    # Only verified auth-service roles supply the RPC scope; there is no body
    # from which a caller could choose another actor or enlarge their domains.
    allowed = [domain for domain, role in DOMAIN_ROLES.items() if role in caller.roles]
    if not allowed:
        raise _forbidden()
    try:
        return service.clear_arrangement_review(str(review_id), caller.id, allowed)
    except ArrangementReviewActionError as error:
        if error.code == "P0003":
            raise _forbidden() from error
        if error.code == "P0002":
            raise HTTPException(
                404,
                detail={
                    "code": "ARRANGEMENT_REVIEW_NOT_FOUND",
                    "message": "Arrangement review is not accessible",
                },
            ) from error
        raise HTTPException(
            409,
            detail={
                "code": "ARRANGEMENT_REVIEW_ALREADY_CLEARED",
                "message": "Arrangement review has already been cleared",
            },
        ) from error
