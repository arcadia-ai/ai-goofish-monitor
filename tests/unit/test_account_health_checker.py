import asyncio

from src.services import account_health_checker
from src.services.search_probe import SearchProbeResult


class FakeContext:
    def __init__(self):
        self.page = object()
        self.new_context_kwargs = None

    async def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, context: FakeContext):
        self.context = context
        self.closed = False

    async def new_context(self, **kwargs):
        self.context.new_context_kwargs = kwargs
        return self.context

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser):
        self.browser = browser
        self.launch_kwargs = None

    async def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self, chromium: FakeChromium):
        self.chromium = chromium


class FakePlaywrightManager:
    def __init__(self, playwright: FakePlaywright):
        self.playwright = playwright

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_health_checker_uses_shared_probe(monkeypatch, tmp_path) -> None:
    account_path = tmp_path / "buyer.json"
    account_path.write_text('{"cookies": []}', encoding="utf-8")
    context = FakeContext()
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    manager = FakePlaywrightManager(FakePlaywright(chromium))
    prepared = []

    async def fake_prepare(target_context):
        prepared.append(target_context)

    async def fake_probe(page, keyword):
        assert page is context.page
        assert keyword == "手机"
        return SearchProbeResult("available", "search ready")

    monkeypatch.setattr(account_health_checker, "async_playwright", lambda: manager)
    monkeypatch.setattr(account_health_checker, "prepare_search_context", fake_prepare)
    monkeypatch.setattr(account_health_checker, "probe_search_page", fake_probe)

    result = asyncio.run(account_health_checker.check_account_health(str(account_path)))

    assert result == {"status": "available", "message": "search ready"}
    assert prepared == [context]
    assert browser.closed is True
    assert context.new_context_kwargs["storage_state"] == str(account_path)


def test_health_checker_does_not_replay_request_scoped_snapshot_headers(
    monkeypatch, tmp_path
) -> None:
    account_path = tmp_path / "enhanced.json"
    account_path.write_text(
        """{
            "cookies": [],
            "env": {"navigator": {"userAgent": "Snapshot UA"}},
            "headers": {
                "Accept": "text/html",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.goofish.com/",
                "Sec-Fetch-Dest": "document",
                "User-Agent": "Snapshot UA"
            }
        }""",
        encoding="utf-8",
    )
    context = FakeContext()
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    manager = FakePlaywrightManager(FakePlaywright(chromium))

    async def fake_prepare(target_context):
        return None

    async def fake_probe(page, keyword):
        return SearchProbeResult("available", "search ready")

    monkeypatch.setattr(account_health_checker, "async_playwright", lambda: manager)
    monkeypatch.setattr(account_health_checker, "prepare_search_context", fake_prepare)
    monkeypatch.setattr(account_health_checker, "probe_search_page", fake_probe)

    result = asyncio.run(account_health_checker.check_account_health(str(account_path)))

    assert result["status"] == "available"
    assert context.new_context_kwargs["storage_state"] == {"cookies": []}
    assert context.new_context_kwargs["user_agent"] == "Snapshot UA"
    assert "extra_http_headers" not in context.new_context_kwargs


def test_health_checker_rejects_invalid_state_file(tmp_path) -> None:
    account_path = tmp_path / "broken.json"
    account_path.write_text("not-json", encoding="utf-8")

    result = asyncio.run(account_health_checker.check_account_health(str(account_path)))

    assert result["status"] == "invalid_file"
