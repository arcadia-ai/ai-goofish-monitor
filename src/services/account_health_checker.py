"""Manual, read-only Goofish account health probe."""
from __future__ import annotations

import json

from playwright.async_api import async_playwright

from src.config import RUN_HEADLESS
from src.scraper import (
    _build_context_overrides,
    _clean_kwargs,
    _default_context_options,
    _resolve_browser_channel,
)
from src.services.search_probe import (
    prepare_search_context,
    probe_search_page,
    search_browser_launch_args,
)


async def check_account_health(account_path: str) -> dict[str, str]:
    try:
        with open(account_path, "r", encoding="utf-8") as state_file:
            snapshot = json.load(state_file)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_file", "message": f"登录态文件无法读取: {exc}"}

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=RUN_HEADLESS,
                args=search_browser_launch_args(),
                channel=_resolve_browser_channel(),
            )
            try:
                context_kwargs = _default_context_options()
                storage_state = account_path
                if isinstance(snapshot, dict) and any(
                    key in snapshot for key in ("env", "headers", "page", "storage")
                ):
                    storage_state = {"cookies": snapshot.get("cookies", [])}
                    context_kwargs.update(_build_context_overrides(snapshot))
                context = await browser.new_context(
                    storage_state=storage_state,
                    **_clean_kwargs(context_kwargs),
                )
                await prepare_search_context(context)
                page = await context.new_page()
                result = await probe_search_page(page, "手机")
                return {"status": result.status, "message": result.message}
            finally:
                await browser.close()
    except Exception as exc:
        return {"status": "error", "message": f"账号检测失败: {exc}"}
