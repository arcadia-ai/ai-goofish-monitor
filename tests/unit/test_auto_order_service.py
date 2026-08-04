import asyncio
from decimal import Decimal

from src.services.auto_order_service import AutoOrderCoordinator
from src.services.goofish_order_executor import OrderExecutionResult


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    async def execute(self, **_kwargs):
        self.calls += 1
        return OrderExecutionResult(
            "submitted_unpaid", "submitted_unpaid", Decimal("88"), "ORDER-1"
        )


def _task(**overrides):
    task = {
        "id": 1,
        "task_name": "内存条",
        "keyword": "DDR4",
        "decision_mode": "ai",
        "account_strategy": "fixed",
        "account_state_file": "state/buyer.json",
        "auto_order_enabled": True,
        "auto_order_score_threshold": 85,
        "auto_order_max_price": "100",
        "auto_order_max_per_run": 1,
    }
    task.update(overrides)
    return task


def _record(item_id="1001"):
    return {
        "商品信息": {
            "商品ID": item_id,
            "商品标题": "DDR4 16G",
            "商品链接": f"https://www.goofish.com/item?id={item_id}",
            "当前售价": "88",
        }
    }


def test_coordinator_is_idempotent_and_enforces_per_run_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    monkeypatch.setenv("AUTO_ORDER_MASTER_ENABLED", "true")
    executor = FakeExecutor()
    coordinator = AutoOrderCoordinator(
        task=_task(), context=object(), executor_factory=lambda: executor
    )

    async def run():
        first = await coordinator.handle(
            _record(), {"is_recommended": True, "value_score": 90}
        )
        duplicate = await coordinator.handle(
            _record(), {"is_recommended": True, "value_score": 90}
        )
        over_limit = await coordinator.handle(
            _record("1002"), {"is_recommended": True, "value_score": 90}
        )
        return first, duplicate, over_limit

    first, duplicate, over_limit = asyncio.run(run())
    assert first["status"] == "submitted_unpaid"
    assert first["attempt_count"] == 1
    assert duplicate is None
    assert over_limit is None
    assert executor.calls == 1
