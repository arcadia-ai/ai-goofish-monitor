"""Per-task orchestration for automatic unpaid-order submission."""
from __future__ import annotations

import asyncio
import os

from src.infrastructure.persistence.storage_names import build_result_filename
from src.services.account_health_service import account_name_from_path, record_account_health
from src.services.auto_order_policy import evaluate_auto_order, parse_money
from src.services.goofish_order_executor import GoofishOrderExecutor, PlaywrightOrderPageAdapter
from src.services.order_record_service import reserve_order_record, update_order_record


def auto_order_master_enabled() -> bool:
    return str(os.getenv("AUTO_ORDER_MASTER_ENABLED", "false")).strip().lower() in {
        "1", "true", "yes", "on"
    }


class AutoOrderCoordinator:
    def __init__(self, *, task: dict, context, executor_factory=None):
        self.task = task
        self.context = context
        self.attempts_in_run = 0
        self._lock = asyncio.Lock()
        self._executor_factory = executor_factory or (
            lambda: GoofishOrderExecutor(PlaywrightOrderPageAdapter(context))
        )

    async def handle(self, record: dict, analysis: dict) -> dict | None:
        item = record.get("商品信息", {}) or {}
        async with self._lock:
            decision = evaluate_auto_order(
                self.task,
                analysis,
                item,
                master_enabled=auto_order_master_enabled(),
                attempts_in_run=self.attempts_in_run,
            )
            if not decision.eligible:
                return None

            account_path = str(self.task["account_state_file"])
            reserved = reserve_order_record(
                task_id=self.task.get("id"),
                task_name=self.task.get("task_name", "未命名任务"),
                account_name=account_name_from_path(account_path),
                account_path=account_path,
                result_filename=build_result_filename(self.task.get("keyword", "")),
                item_id=str(item.get("商品ID")),
                title=item.get("商品标题"),
                item_link=item.get("商品链接"),
                value_score=decision.value_score,
                score_threshold=self.task.get("auto_order_score_threshold", 85),
                observed_price=decision.observed_price,
                max_price=parse_money(self.task.get("auto_order_max_price")),
            )
            if reserved is None:
                return None

            self.attempts_in_run += 1
            update_order_record(
                reserved["id"], status="submitting", increment_attempt=True
            )
            try:
                result = await self._executor_factory().execute(
                    item_link=item.get("商品链接", ""),
                    observed_price=decision.observed_price,
                    max_price=parse_money(self.task.get("auto_order_max_price")),
                )
            except Exception as exc:
                reason = f"order_execution_error:{type(exc).__name__}"
                print(f"[自动锁单] 执行器异常: {reason}")
                return update_order_record(
                    reserved["id"], status="failed", reason=reason
                )

            stored = update_order_record(
                reserved["id"],
                status=result.status,
                reason=result.reason,
                payable_total=float(result.payable_total) if result.payable_total is not None else None,
                platform_order_id=result.platform_order_id,
            )
            if result.reason == "login_required":
                record_account_health(account_path, "expired", source="order", message=result.reason)
            elif result.reason in {"risk_controlled", "captcha_required"}:
                record_account_health(account_path, "risk_controlled", source="order", message=result.reason)
            print(
                f"[自动锁单] 任务={self.task.get('task_name')} 商品={item.get('商品ID')} "
                f"状态={stored['status']} 原因={stored.get('reason') or '-'}"
            )
            return stored
