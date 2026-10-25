"""SCRUM-40 shared timer mechanics, independent of SCRUM-38 domain logic."""

import asyncio
from threading import Event, get_ident

from app.services.periodic_task_runner import PeriodicTaskRunner


# AC1-X2 (cross-cutting): a failing named handler cannot suppress a later story's independent pass or subsequent sweeps.
def test_run_once_isolates_named_handler_failure():
    calls = []

    def failed():
        calls.append("completion")
        raise RuntimeError("prepared handler outage")

    def later():
        calls.append("registration")

    runner = PeriodicTaskRunner({"completion": failed, "registration": later})
    runner.run_once()
    runner.run_once()
    assert calls == ["completion", "registration", "completion", "registration"]


# AC1-X3 (cross-cutting): cancellation waits for offloaded active work, then stops before another handler can run.
def test_async_cancel_waits_for_active_handler_without_blocking_event_loop():
    entered = Event()
    release = Event()
    finished = Event()
    calls = []
    threads = []
    main_thread = get_ident()

    def active():
        threads.append(get_ident())
        calls.append("active")
        entered.set()
        assert release.wait(3), "test fixture did not release the active handler"
        finished.set()

    def forbidden_later():
        calls.append("later")

    async def exercise():
        runner = PeriodicTaskRunner(
            {"active": active, "later": forbidden_later}, interval_seconds=7
        )
        task = asyncio.create_task(runner.run_forever())
        try:
            assert await asyncio.to_thread(entered.wait, 1), "timer never ran its handler"
            assert not finished.is_set()
            assert len(threads) == 1 and threads[0] != main_thread
            task.cancel()
            # An event-loop turn lets cancellation reach its await; no wall-clock scheduling guess.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), "cancellation abandoned active synchronous work"
            release.set()
            try:
                await asyncio.wait_for(task, timeout=1)
            except asyncio.CancelledError:
                pass
            assert finished.is_set()
            assert calls == ["active"]
        finally:
            release.set()
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1)
                except asyncio.CancelledError:
                    pass

    asyncio.run(exercise())


# AC1-B4 (boundary): the configured interval controls repeat scheduling instead of a hidden hard-coded default.
def test_async_loop_uses_nondefault_interval(monkeypatch):
    calls = []
    sleeps = []

    def handler():
        calls.append("pass")

    async def sleep(delay):
        sleeps.append(delay)
        raise asyncio.CancelledError

    async def exercise():
        runner = PeriodicTaskRunner({"completion": handler}, interval_seconds=7)
        monkeypatch.setattr(asyncio, "sleep", sleep)
        try:
            await runner.run_forever()
        except asyncio.CancelledError:
            pass

    asyncio.run(exercise())
    assert calls == ["pass"]
    assert sleeps == [7]
