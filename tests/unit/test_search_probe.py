import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.services.search_probe import (
    SearchProbeResult,
    prepare_search_context,
    probe_search_page,
)


class FakeRequest:
    method = "POST"


class FakeResponse:
    def __init__(self, payload: dict, *, ok: bool = True):
        self.url = (
            "https://h5api.m.goofish.com/h5/"
            "mtop.taobao.idlemtopsearch.pc.search/1.0/?test=1"
        )
        self.request = FakeRequest()
        self.ok = ok
        self.payload = payload

    async def json(self) -> dict:
        return self.payload


class FakeLocator:
    def __init__(self, visibilities: list[bool]):
        self._visibilities = visibilities

    async def count(self) -> int:
        return len(self._visibilities)

    def nth(self, index: int):
        return FakeLocator([self._visibilities[index]])

    async def is_visible(self) -> bool:
        return bool(self._visibilities and self._visibilities[0])


class FakeResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @property
    def value(self):
        return self._resolve()

    async def _resolve(self):
        return self.response


class FakePage:
    def __init__(
        self,
        response: FakeResponse,
        *,
        final_url: str = "https://www.goofish.com/search?q=test",
        risk_visibilities: list[bool] | None = None,
        search_error: Exception | None = None,
    ):
        self.response = response
        self.final_url = final_url
        self.risk_visibilities = risk_visibilities or []
        self.search_error = search_error
        self.url = "about:blank"
        self.goto_calls: list[str] = []
        self.evaluations: list[str] = []

    async def goto(self, url: str, **_kwargs):
        self.goto_calls.append(url)
        self.url = self.final_url if "/search?" in url else url
        if "/search?" in url and self.search_error is not None:
            raise self.search_error

    async def evaluate(self, script: str):
        self.evaluations.append(script)

    def expect_response(self, predicate, timeout: int):
        assert timeout == 30000
        assert predicate(self.response) is True
        return FakeResponseContext(self.response)

    def locator(self, _selector: str):
        return FakeLocator(self.risk_visibilities)


class FakeContext:
    def __init__(self):
        self.scripts: list[str] = []

    async def add_init_script(self, script: str):
        self.scripts.append(script)


async def _no_wait(_minimum: float, _maximum: float) -> None:
    return None


def _probe(page: FakePage) -> SearchProbeResult:
    return asyncio.run(
        probe_search_page(
            page,
            "手机",
            logger=lambda _message: None,
            wait_between=_no_wait,
        )
    )


def test_probe_uses_task_warmup_and_accepts_empty_result_list() -> None:
    response = FakeResponse({"data": {"resultList": []}})
    page = FakePage(response)

    result = _probe(page)

    assert result.status == "available"
    assert result.response is response
    assert page.goto_calls == [
        "https://www.goofish.com/",
        "https://www.goofish.com/search?q=%E6%89%8B%E6%9C%BA",
    ]
    assert len(page.evaluations) == 1


def test_probe_classifies_login_redirect() -> None:
    page = FakePage(
        FakeResponse({"data": {"resultList": []}}),
        final_url="https://passport.goofish.com/mini_login.htm",
    )

    result = _probe(page)

    assert result.status == "expired"


def test_probe_only_classifies_visible_dom_or_api_risk_control() -> None:
    hidden_dom_result = _probe(
        FakePage(
            FakeResponse({"data": {"resultList": []}}),
            risk_visibilities=[False],
        )
    )
    dom_result = _probe(
        FakePage(
            FakeResponse({"data": {"resultList": []}}),
            risk_visibilities=[False, True],
        )
    )
    api_result = _probe(
        FakePage(
            FakeResponse(
                {
                    "ret": ["FAIL_SYS_USER_VALIDATE::RGV587_ERROR"],
                    "data": {},
                }
            )
        )
    )

    assert hidden_dom_result.status == "available"
    assert dom_result.status == "risk_controlled"
    assert api_result.status == "risk_controlled"


def test_probe_rejects_invalid_search_response_structure() -> None:
    result = _probe(FakePage(FakeResponse({"data": {}})))

    assert result.status == "error"
    assert "商品列表结构" in result.message


def test_probe_timeout_remains_generic_error() -> None:
    result = _probe(
        FakePage(
            FakeResponse({"data": {"resultList": []}}),
            search_error=PlaywrightTimeoutError("search timeout"),
        )
    )

    assert result.status == "error"
    assert "搜索能力检测超时" in result.message


def test_prepare_search_context_installs_shared_script() -> None:
    context = FakeContext()

    asyncio.run(prepare_search_context(context))

    assert len(context.scripts) == 1
    assert "navigator, 'webdriver'" in context.scripts[0]
