"""User-triggered retry for a previously blocked or failed order record."""
from __future__ import annotations

import json
from decimal import Decimal

from playwright.async_api import async_playwright

from src.config import RUN_HEADLESS
from src.scraper import (
    _build_context_overrides,
    _clean_kwargs,
    _default_context_options,
    _resolve_browser_channel,
)
from src.services.goofish_order_executor import GoofishOrderExecutor, PlaywrightOrderPageAdapter
from src.services.order_record_service import prepare_manual_retry, update_order_record


async def retry_order_record(record: dict) -> dict:
    prepared = prepare_manual_retry(record["id"])
    if prepared is None:
        raise ValueError("当前锁单状态不允许重试。")
    update_order_record(record["id"], status="submitting", increment_attempt=True)
    browser = None
    try:
        with open(record["account_path"], "r", encoding="utf-8") as state_file:
            snapshot = json.load(state_file)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=RUN_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
                channel=_resolve_browser_channel(),
            )
            context_kwargs = _default_context_options()
            storage_state = record["account_path"]
            if isinstance(snapshot, dict) and any(
                key in snapshot for key in ("env", "headers", "page", "storage")
            ):
                storage_state = {"cookies": snapshot.get("cookies", [])}
                context_kwargs.update(_build_context_overrides(snapshot))
            context = await browser.new_context(
                storage_state=storage_state,
                **_clean_kwargs(context_kwargs),
            )
            result = await GoofishOrderExecutor(
                PlaywrightOrderPageAdapter(context)
            ).execute(
                item_link=record["item_link"],
                observed_price=Decimal(str(record["observed_price"])),
                max_price=Decimal(str(record["max_price"])),
            )
            return update_order_record(
                record["id"],
                status=result.status,
                reason=result.reason,
                payable_total=float(result.payable_total) if result.payable_total is not None else None,
                platform_order_id=result.platform_order_id,
            )
    except Exception as exc:
        reason = f"manual_retry_error:{type(exc).__name__}"
        print(f"[自动锁单] 人工重试失败: {reason}")
        return update_order_record(record["id"], status="failed", reason=reason)
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception as exc:
                print(f"[自动锁单] 人工重试浏览器关闭失败: {type(exc).__name__}")
