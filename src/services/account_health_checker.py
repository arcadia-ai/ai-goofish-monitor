"""Manual, read-only Goofish account health probe."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from src.config import RUN_HEADLESS
from src.scraper import (
    _build_context_overrides,
    _build_extra_headers,
    _clean_kwargs,
    _default_context_options,
    _is_login_url,
    _resolve_browser_channel,
)


async def check_account_health(account_path: str) -> dict[str, str]:
    try:
        with open(account_path, "r", encoding="utf-8") as state_file:
            snapshot = json.load(state_file)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid_file", "message": f"登录态文件无法读取: {exc}"}

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
    ]
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=RUN_HEADLESS,
                args=launch_args,
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
                    headers = _build_extra_headers(snapshot.get("headers"))
                    if headers:
                        context_kwargs["extra_http_headers"] = headers
                context = await browser.new_context(
                    storage_state=storage_state,
                    **_clean_kwargs(context_kwargs),
                )
                page = await context.new_page()
                await page.goto(
                    f"https://www.goofish.com/search?{urlencode({'q': '手机'})}",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                if _is_login_url(page.url):
                    return {"status": "expired", "message": "登录态已跳转到登录页面。"}
                if await page.locator(
                    "div.baxia-dialog-mask, div.J_MIDDLEWARE_FRAME_WIDGET"
                ).count():
                    return {"status": "risk_controlled", "message": "检测到闲鱼风控验证。"}
                await page.wait_for_selector("text=新发布", timeout=15000)
                return {"status": "available", "message": "登录态可正常访问搜索页。"}
            finally:
                await browser.close()
    except PlaywrightTimeoutError as exc:
        return {"status": "error", "message": f"账号检测超时: {exc}"}
    except Exception as exc:
        return {"status": "error", "message": f"账号检测失败: {exc}"}
