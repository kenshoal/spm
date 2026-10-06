"""Dict-to-dataclass conversion for equipment_reservations rows (SCRUM-10).

Kept out of app/availability.py so that module stays free of I/O types;
both the status router and the availability-check router convert their
query results through here.
"""

from datetime import date

from app.availability import Reservation


def reservation_from_row(row: dict) -> Reservation:
    """Build a Reservation from a Supabase/FakeSupabase row dict."""
    return Reservation(
        equipment_id=str(row["equipment_id"]),
        quantity=int(row["quantity"]),
        collection_date=date.fromisoformat(row["collection_date"]),
        return_date=date.fromisoformat(row["return_date"]),
    )
