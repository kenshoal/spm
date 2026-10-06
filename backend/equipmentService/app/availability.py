"""Equipment availability calculation (SCRUM-10).

Pure functions: no database or network access, so every date boundary is
unit-tested in CI. See docs/testcases/scrum_10_testcases.md.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

# Team design proposal 1: one fixed transfer/preparation buffer (Discussion #2).
TRANSFER_DAYS = 1


@dataclass(frozen=True)
class Venue:
    id: str
    name: str
    location: str


@dataclass(frozen=True)
class EquipmentRow:
    id: str
    type: str
    total_owned_quantity: int
    home_location: str
    operational_status: str = "AVAILABLE"


@dataclass(frozen=True)
class Reservation:
    equipment_id: str
    quantity: int
    collection_date: date
    return_date: date


@dataclass(frozen=True)
class RequestedItem:
    type: str
    quantity: int


def norm(text: str) -> str:
    """Compare free text ignoring case and extra spaces."""
    return " ".join(text.split()).casefold()


def hold_window(
    start: date,
    end: date,
    needs_transfer: bool,
    transfer_days: int = TRANSFER_DAYS,
) -> tuple[date, date]:
    """Inclusive (hold_start, hold_end) for one catalogue row."""
    buffer = transfer_days if needs_transfer else 0
    return (start - timedelta(days=1 + buffer), end)


def needs_transfer(
    home_location: str, event_venue: Venue, venues: Sequence[Venue]
) -> bool:
    """True when the row is based in a different building from the event."""
    key = norm(home_location)
    name_buildings = {norm(v.location) for v in venues if norm(v.name) == key}
    if len(name_buildings) > 1:
        return True  # ambiguous name: assume the transfer day (AC5-P9)
    if len(name_buildings) == 1:
        building = next(iter(name_buildings))  # names before locations (AC5-P10)
    elif any(norm(v.location) == key for v in venues):
        building = key
    else:
        return False  # store stock: D-1 only (AC5-P8)
    return building != norm(event_venue.location)


def committed_peak(
    equipment_id: str, reservations: Sequence[Reservation], start: date, end: date
) -> int:
    """Units of one row reserved on its busiest day within [start, end]."""
    relevant = [
        r
        for r in reservations
        if r.equipment_id == equipment_id
        and r.collection_date <= end
        and r.return_date >= start
    ]
    if not relevant:
        return 0
    # The peak always falls on some reservation's first day inside the window.
    candidates = {max(r.collection_date, start) for r in relevant}
    return max(
        sum(
            r.quantity
            for r in relevant
            if r.collection_date <= day <= r.return_date
        )
        for day in candidates
    )


def check_availability(
    *,
    rows: Sequence[EquipmentRow],
    reservations: Sequence[Reservation],
    start_date: date,
    end_date: date,
    event_venue: Venue,
    venues: Sequence[Venue],
    items: Sequence[RequestedItem],
    transfer_days: int = TRANSFER_DAYS,
) -> dict[str, dict[str, int]]:
    """{requested type: {requested, available, shortfall}}, keyed as requested."""
    result: dict[str, dict[str, int]] = {}
    for item in items:
        key = norm(item.type)
        available = 0
        for row in rows:
            if row.operational_status != "AVAILABLE" or norm(row.type) != key:
                continue
            transfer = needs_transfer(row.home_location, event_venue, venues)
            hold_start, hold_end = hold_window(
                start_date, end_date, transfer, transfer_days
            )
            peak = committed_peak(row.id, reservations, hold_start, hold_end)
            available += max(0, row.total_owned_quantity - peak)
        result[item.type] = {
            "requested": item.quantity,
            "available": available,
            "shortfall": max(0, item.quantity - available),
        }
    return result
