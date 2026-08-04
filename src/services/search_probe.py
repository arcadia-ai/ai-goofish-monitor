"""Shared task-like probe for checking whether Goofish search is usable."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.services.search_pagination import is_search_results_response
from src.utils import log_time, random_sleep


RISK_CONTROL_SELECTOR = (
    "div.baxia-dialog-mask, "
    "div.J_MIDDLEWARE_FRAME_WIDGET, "
    "iframe[src*='captcha']"
)

SEARCH_CONTEXT_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
    window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};
    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});

    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : originalQuery(parameters)
    );
"""


@dataclass(frozen=True)
class SearchProbeResult:
    status: str
    message: str
    response: Any | None = None


def is_login_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return "passport.goofish.com" in lowered or "mini_login" in lowered


def search_browser_launch_args() -> list[str]:
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
    ]


async def prepare_search_context(context: Any) -> None:
    await context.add_init_script(SEARCH_CONTEXT_INIT_SCRIPT)


async def _has_risk_control(page: Any) -> bool:
    candidates = page.locator(RISK_CONTROL_SELECTOR)
    for index in range(await candidates.count()):
        if await candidates.nth(index).is_visible():
            return True
    return False


async def _classify_response(page: Any, response: Any) -> SearchProbeResult:
    if is_login_url(getattr(page, "url", "")):
        return SearchProbeResult("expired", "登录态已跳转到登录页面。")
    if await _has_risk_control(page):
        return SearchProbeResult("risk_controlled", "检测到闲鱼风控验证。")
    if not getattr(response, "ok", False):
        return SearchProbeResult("error", "搜索接口返回非成功状态。")

    try:
        payload = await response.json()
    except Exception as exc:
        return SearchProbeResult("error", f"搜索接口响应无法解析: {exc}")

    if "FAIL_SYS_USER_VALIDATE" in str(payload.get("ret", [])):
        return SearchProbeResult("risk_controlled", "搜索接口触发闲鱼风控验证。")

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("resultList"), list):
        return SearchProbeResult("error", "搜索接口响应缺少有效的商品列表结构。")

    return SearchProbeResult(
        "available",
        "账号可正常访问闲鱼搜索接口。",
        response=response,
    )


async def probe_search_page(
    page: Any,
    keyword: str,
    *,
    logger: Callable[[str], None] = log_time,
    wait_between: Callable[[float, float], Awaitable[None]] = random_sleep,
) -> SearchProbeResult:
    """Run the same warm-up and search probe used by monitoring tasks."""
    try:
        logger("步骤 0 - 模拟真实用户访问首页...")
        await page.goto(
            "https://www.goofish.com/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        logger("[反爬] 在首页停留，模拟浏览...")
        await wait_between(1, 2)
        await page.evaluate("window.scrollBy(0, Math.random() * 500 + 200)")
        await wait_between(1, 2)

        logger("步骤 1 - 导航到搜索结果页...")
        search_url = f"https://www.goofish.com/search?{urlencode({'q': keyword})}"
        logger(f"目标URL: {search_url}")
        async with page.expect_response(
            is_search_results_response,
            timeout=30000,
        ) as response_info:
            await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

        if is_login_url(getattr(page, "url", "")):
            return SearchProbeResult("expired", "登录态已跳转到登录页面。")

        response = await response_info.value
        return await _classify_response(page, response)
    except PlaywrightTimeoutError as exc:
        if is_login_url(getattr(page, "url", "")):
            return SearchProbeResult("expired", "登录态已跳转到登录页面。")
        if await _has_risk_control(page):
            return SearchProbeResult("risk_controlled", "检测到闲鱼风控验证。")
        return SearchProbeResult("error", f"搜索能力检测超时: {exc}")
