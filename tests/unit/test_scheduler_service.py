from __future__ import annotations

import asyncio
from datetime import datetime

from src.failure_guard import SkipDecision
from src.services.process_service import TaskStartPausedError
from src.services.scheduler_service import SchedulerService


def test_scheduler_treats_failure_guard_pause_as_expected_control_flow():
    class PausedProcessService:
        async def start_task(self, _task_id: int, task_name: str) -> bool:
            decision = SkipDecision(
                skip=True,
                should_notify=False,
                reason="old timeout",
                paused_until=datetime(2026, 8, 5, 11, 46, 22),
                consecutive_failures=3,
            )
            raise TaskStartPausedError(task_name, decision, threshold=3)

    service = SchedulerService(PausedProcessService())

    assert asyncio.run(service._run_task(0, "task-a")) is None
