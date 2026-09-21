"""Configurable adapter for actual venue allocations owned by another service."""

from datetime import date
from typing import Annotated, Protocol

import httpx
from fastapi import Depends, HTTPException
from pydantic import ValidationError

from app.availability_models import AllocationPage, EventAllocation
from app.config import Settings, get_settings


class EventAllocationSource(Protocol):
    def list_for_period(
        self, venue_id: str, start_date: date, end_date: date
    ) -> list[EventAllocation]: ...


class HttpEventAllocationSource:
    def __init__(
        self,
        url: str | None,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url, self.token, self.transport = url, token, transport

    def list_for_period(
        self, venue_id: str, start_date: date, end_date: date
    ) -> list[EventAllocation]:
        if self.url is None:
            raise HTTPException(503, "Event allocation lookup is not configured")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        params = {
            "venue_id": venue_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        allocations: list[EventAllocation] = []
        seen_cursors: set[str] = set()
        try:
            with httpx.Client(timeout=5, transport=self.transport) as client:
                for _ in range(1000):
                    response = client.get(self.url, params=params, headers=headers)
                    response.raise_for_status()
                    page = AllocationPage.model_validate(response.json())
                    allocations.extend(page.allocations)
                    if page.next_cursor is None:
                        return allocations
                    if page.next_cursor in seen_cursors:
                        raise ValueError("Repeated allocation cursor")
                    seen_cursors.add(page.next_cursor)
                    params["cursor"] = page.next_cursor
                raise ValueError("Allocation pagination limit exceeded")
        except (httpx.HTTPError, ValidationError, ValueError):
            # Do not leak service URLs, tokens, response bodies, or partial results.
            raise HTTPException(502, "Event allocation lookup failed") from None


def get_event_allocations(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventAllocationSource:
    return HttpEventAllocationSource(
        str(settings.event_allocations_url) if settings.event_allocations_url else None,
        settings.event_allocations_token.get_secret_value()
        if settings.event_allocations_token
        else None,
    )
