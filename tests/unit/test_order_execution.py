import asyncio
from decimal import Decimal

import pytest

from src.services.goofish_order_executor import GoofishOrderExecutor


class FakeOrderAdapter:
    def __init__(self, **overrides):
        self.state = {
            "login_required": False,
            "risk_controlled": False,
            "unavailable": False,
            "captcha": False,
            "requires_specification": False,
            "requires_address": False,
            "item_price": Decimal("100"),
            "payable_total": Decimal("100"),
            "order_id": "ORDER-1",
            "unpaid": True,
        }
        self.state.update(overrides)
        self.submit_count = 0

    async def open_item(self, _url): pass
    async def is_login_required(self): return self.state["login_required"]
    async def is_risk_controlled(self): return self.state["risk_controlled"]
    async def is_unavailable(self): return self.state["unavailable"]
    async def begin_purchase(self): return True
    async def has_captcha(self): return self.state["captcha"]
    async def requires_specification(self): return self.state["requires_specification"]
    async def requires_address_selection(self): return self.state["requires_address"]
    async def read_item_price(self): return self.state["item_price"]
    async def read_payable_total(self): return self.state["payable_total"]
    async def submit_order_once(self): self.submit_count += 1
    async def read_submission_result(self):
        return self.state["order_id"], self.state["unpaid"]
    async def close(self):
        if self.state.get("close_error"):
            raise RuntimeError("close failed")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"requires_specification": True}, "specification_required"),
        ({"requires_address": True}, "address_selection_required"),
        ({"captcha": True}, "captcha_required"),
        ({"risk_controlled": True}, "risk_controlled"),
        ({"unavailable": True}, "item_unavailable"),
        ({"item_price": Decimal("101")}, "item_price_changed"),
        ({"payable_total": Decimal("101")}, "payable_total_above_limit"),
    ],
)
def test_order_executor_fails_closed_before_submit(overrides, reason):
    adapter = FakeOrderAdapter(**overrides)
    result = asyncio.run(
        GoofishOrderExecutor(adapter).execute(
            item_link="https://www.goofish.com/item?id=1",
            observed_price=Decimal("100"),
            max_price=Decimal("100"),
        )
    )
    assert result.status == "blocked"
    assert result.reason == reason
    assert adapter.submit_count == 0


def test_order_executor_submits_once_and_requires_positive_success_signal():
    adapter = FakeOrderAdapter()
    result = asyncio.run(
        GoofishOrderExecutor(adapter).execute(
            item_link="https://www.goofish.com/item?id=1",
            observed_price=Decimal("100"),
            max_price=Decimal("100"),
        )
    )
    assert result.status == "submitted_unpaid"
    assert result.platform_order_id == "ORDER-1"
    assert adapter.submit_count == 1

    unknown = FakeOrderAdapter(order_id=None, unpaid=False)
    unknown_result = asyncio.run(
        GoofishOrderExecutor(unknown).execute(
            item_link="https://www.goofish.com/item?id=1",
            observed_price=Decimal("100"),
            max_price=Decimal("100"),
        )
    )
    assert unknown_result.status == "submitting"
    assert unknown_result.reason == "submission_unconfirmed"
    assert unknown.submit_count == 1


def test_order_executor_keeps_confirmed_result_when_page_close_fails():
    adapter = FakeOrderAdapter(close_error=True)
    result = asyncio.run(
        GoofishOrderExecutor(adapter).execute(
            item_link="https://www.goofish.com/item?id=1",
            observed_price=Decimal("100"),
            max_price=Decimal("100"),
        )
    )

    assert result.status == "submitted_unpaid"
    assert result.platform_order_id == "ORDER-1"
    assert adapter.submit_count == 1
