"""Process-wide venue write lock for the in-memory stores.

The database serialises block creation and booking approval by locking the
venues row (0024). In memory mode this lock plays the same role, so a block
and an approval, or two approvals, cannot interleave between check and save.
"""

from __future__ import annotations

import threading

venue_write_lock = threading.RLock()
