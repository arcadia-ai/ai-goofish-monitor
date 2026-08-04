"""Fail-closed order state machine and its Playwright page adapter."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from src.services.auto_order_policy import parse_money


@dataclass(frozen=True)
class OrderExecutionResult:
    status: str
    reason: str
    payable_total: Decimal | None = None
    platform_order_id: str | None = None


class OrderPageAdapter(Protocol):
    async def open_item(self, url: str): ...
    async def is_login_required(self) -> bool: ...
    async def is_risk_controlled(self) -> bool: ...
    async def is_unavailable(self) -> bool: ...
    async def begin_purchase(self) -> bool: ...
    async def has_captcha(self) -> bool: ...
    async def requires_specification(self) -> bool: ...
    async def requires_address_selection(self) -> bool: ...
    async def read_item_price(self) -> Decimal | None: ...
    async def read_payable_total(self) -> Decimal | None: ...
    async def submit_order_once(self): ...
    async def read_submission_result(self) -> tuple[str | None, bool]: ...
    async def close(self): ...


class GoofishOrderExecutor:
    def __init__(self, adapter: OrderPageAdapter):
        self.adapter = adapter

    async def execute(
        self,
        *,
        item_link: str,
        observed_price: Decimal,
        max_price: Decimal,
    ) -> OrderExecutionResult:
        try:
            await self.adapter.open_item(item_link)
            if await self.adapter.is_login_required():
                return OrderExecutionResult("blocked", "login_required")
            if await self.adapter.is_risk_controlled():
                return OrderExecutionResult("blocked", "risk_controlled")
            if await self.adapter.is_unavailable():
                return OrderExecutionResult("blocked", "item_unavailable")
            if not await self.adapter.begin_purchase():
                return OrderExecutionResult("blocked", "purchase_action_unavailable")
            if await self.adapter.has_captcha():
                return OrderExecutionResult("blocked", "captcha_required")
            if await self.adapter.requires_specification():
                return OrderExecutionResult("blocked", "specification_required")
            if await self.adapter.requires_address_selection():
                return OrderExecutionResult("blocked", "address_selection_required")

            item_price = await self.adapter.read_item_price()
            payable_total = await self.adapter.read_payable_total()
            if item_price is None or payable_total is None:
                return OrderExecutionResult("blocked", "confirmation_price_unavailable")
            if item_price != observed_price:
                return OrderExecutionResult("blocked", "item_price_changed", payable_total)
            if payable_total > max_price:
                return OrderExecutionResult("blocked", "payable_total_above_limit", payable_total)

            await self.adapter.submit_order_once()
            order_id, unpaid = await self.adapter.read_submission_result()
            if not order_id and not unpaid:
                # The click may already have reached the platform. Keep this state
                # non-retryable until the user verifies the account manually.
                return OrderExecutionResult(
                    "submitting", "submission_unconfirmed", payable_total
                )
            return OrderExecutionResult(
                "submitted_unpaid",
                "submitted_unpaid",
                payable_total,
                order_id,
            )
        except Exception as exc:
            return OrderExecutionResult(
                "failed", f"executor_error:{type(exc).__name__}"
            )
        finally:
            try:
                await self.adapter.close()
            except Exception as exc:
                # Closing the isolated order page must never overwrite a confirmed
                # submission result and make the same item appear retryable.
                print(f"[自动锁单] 关闭订单页面失败: {type(exc).__name__}")


class PlaywrightOrderPageAdapter:
    BUY_BUTTON_NAMES = re.compile(r"^(立即购买|马上买)$")
    SUBMIT_BUTTON_NAMES = re.compile(r"^(提交订单|确认购买)$")
    ORDER_ID_PATTERN = re.compile(r"订单(?:编号|号)[:：]?\s*([A-Za-z0-9_-]{6,64})")

    def __init__(self, context):
        self.context = context
        self.page = None

    async def open_item(self, url: str):
        self.page = await self.context.new_page()
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def is_login_required(self) -> bool:
        return "passport.goofish.com" in self.page.url.lower() or "mini_login" in self.page.url.lower()

    async def is_risk_controlled(self) -> bool:
        return bool(await self.page.locator(
            "div.baxia-dialog-mask, div.J_MIDDLEWARE_FRAME_WIDGET"
        ).count())

    async def is_unavailable(self) -> bool:
        return bool(await self.page.get_by_text(
            re.compile(r"^(商品已下架|商品已卖出|宝贝不存在)$")
        ).count())

    async def begin_purchase(self) -> bool:
        button = self.page.get_by_role("button", name=self.BUY_BUTTON_NAMES)
        if await button.count() != 1:
            return False
        await button.click()
        await self.page.wait_for_load_state("domcontentloaded")
        return True

    async def has_captcha(self) -> bool:
        return bool(await self.page.locator(
            "div.baxia-dialog-mask, div.J_MIDDLEWARE_FRAME_WIDGET, iframe[src*='captcha']"
        ).count())

    async def requires_specification(self) -> bool:
        return bool(await self.page.get_by_text(
            re.compile(r"^(选择规格|请选择规格|选择型号|请选择型号)$")
        ).count())

    async def requires_address_selection(self) -> bool:
        return bool(await self.page.get_by_text(
            re.compile(r"^(选择收货地址|请选择收货地址)$")
        ).count())

    async def _read_unique_money(self, selector: str) -> Decimal | None:
        locator = self.page.locator(selector)
        if await locator.count() != 1:
            return None
        return parse_money(await locator.inner_text())

    async def read_item_price(self) -> Decimal | None:
        return await self._read_unique_money(
            "[data-testid='item-price'], [data-order-field='item-price']"
        )

    async def read_payable_total(self) -> Decimal | None:
        return await self._read_unique_money(
            "[data-testid='payable-total'], [data-order-field='payable-total']"
        )

    async def submit_order_once(self):
        button = self.page.get_by_role("button", name=self.SUBMIT_BUTTON_NAMES)
        if await button.count() != 1:
            raise RuntimeError("未找到唯一的提交订单按钮")
        await button.click()
        await self.page.wait_for_load_state("domcontentloaded")

    async def read_submission_result(self) -> tuple[str | None, bool]:
        content = await self.page.inner_text("body")
        match = self.ORDER_ID_PATTERN.search(content)
        unpaid = bool(await self.page.get_by_text(re.compile(r"^(待付款|立即付款|去支付)$")).count())
        return (match.group(1) if match else None), unpaid

    async def close(self):
        if self.page is not None:
            await self.page.close()
