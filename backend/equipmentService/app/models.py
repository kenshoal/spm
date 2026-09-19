from enum import StrEnum


class OperationalStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DAMAGED = "DAMAGED"
    UNDER_REPAIR = "UNDER_REPAIR"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    RETIRED = "RETIRED"
