"""A thin timer for independent synchronous story handlers, without domain rules."""

import asyncio
import logging
import math
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class PeriodicTaskRunner:
    def __init__(
        self,
        handlers: dict[str, Callable[[], Any]],
        *,
        interval_seconds: float = 60,
    ) -> None:
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("Periodic task interval must be finite and positive")
        self._handlers = dict(handlers)
        self._interval_seconds = interval_seconds

    @staticmethod
    def _run_handler(name: str, handler: Callable[[], Any]) -> None:
        try:
            handler()
        except Exception:
            # One story's unavailable dependency must not disable another job.
            logger.exception("Periodic handler %s failed; retrying next pass", name)

    def run_once(self) -> None:
        for name, handler in self._handlers.items():
            self._run_handler(name, handler)

    async def run_forever(self) -> None:
        while True:
            for name, handler in self._handlers.items():
                active = asyncio.create_task(
                    asyncio.to_thread(self._run_handler, name, handler)
                )
                try:
                    await asyncio.shield(active)
                except asyncio.CancelledError:
                    # Cancelling to_thread cannot stop a database write. Wait
                    # for it, even on repeated cancellation, before reporting
                    # shutdown or allowing a replacement pass to start.
                    while not active.done():
                        try:
                            await asyncio.shield(active)
                        except asyncio.CancelledError:
                            continue
                    raise
            await asyncio.sleep(self._interval_seconds)
