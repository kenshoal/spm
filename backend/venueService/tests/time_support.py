"""SCRUM-65 test helper: the times that replace a set of consecutive slots
(AM 07:00-12:00, PM 12:00-18:00, NIGHT 18:00-24:00), so tests written for slots
keep their meaning under the time model."""

from app.slots import slots_to_range


def slot_times(slots) -> dict[str, int]:
    start, end = slots_to_range(slots)
    return {"start_minute": start, "end_minute": end}
