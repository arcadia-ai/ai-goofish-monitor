"""Pure eligibility rules for automatic unpaid-order submission."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class AutoOrderDecision:
    eligible: bool
    reason: str
    value_score: float | None = None
    observed_price: Decimal | None = None


def parse_money(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def evaluate_auto_order(
    task: dict,
    analysis: dict,
    item: dict,
    *,
    master_enabled: bool,
    attempts_in_run: int,
) -> AutoOrderDecision:
    if not master_enabled:
        return AutoOrderDecision(False, "master_disabled")
    if not task.get("auto_order_enabled"):
        return AutoOrderDecision(False, "task_disabled")
    if task.get("decision_mode") != "ai":
        return AutoOrderDecision(False, "ai_mode_required")
    if task.get("account_strategy") != "fixed" or not task.get("account_state_file"):
        return AutoOrderDecision(False, "fixed_account_required")
    if analysis.get("is_recommended") is not True:
        return AutoOrderDecision(False, "not_recommended")

    raw_score = analysis.get("value_score")
    if isinstance(raw_score, bool):
        return AutoOrderDecision(False, "missing_value_score")
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return AutoOrderDecision(False, "missing_value_score")
    if not 0 <= score <= 100:
        return AutoOrderDecision(False, "invalid_value_score")
    threshold = float(task.get("auto_order_score_threshold", 85))
    if score < threshold:
        return AutoOrderDecision(False, "score_below_threshold", score)

    observed_price = parse_money(item.get("当前售价"))
    max_price = parse_money(task.get("auto_order_max_price"))
    if observed_price is None:
        return AutoOrderDecision(False, "missing_item_price", score)
    if observed_price <= 0:
        return AutoOrderDecision(False, "invalid_item_price", score, observed_price)
    if max_price is None or max_price <= 0:
        return AutoOrderDecision(False, "invalid_price_limit", score, observed_price)
    if observed_price > max_price:
        return AutoOrderDecision(False, "price_above_limit", score, observed_price)
    if attempts_in_run >= int(task.get("auto_order_max_per_run", 1)):
        return AutoOrderDecision(False, "run_limit_reached", score, observed_price)
    if not str(item.get("商品ID") or "").strip():
        return AutoOrderDecision(False, "missing_item_id", score, observed_price)
    return AutoOrderDecision(True, "eligible", score, observed_price)
