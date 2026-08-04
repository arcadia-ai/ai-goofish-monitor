from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import accounts


def _client():
    app = FastAPI()
    app.include_router(accounts.router)
    return TestClient(app)


def test_account_list_includes_health_and_cookie_update_resets(monkeypatch, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    account = state_dir / "buyer.json"
    account.write_text('{"cookies": []}', encoding="utf-8")
    monkeypatch.setenv("ACCOUNT_STATE_DIR", str(state_dir))
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))

    accounts.record_account_health(str(account), "expired", source="task")
    client = _client()
    listed = client.get("/api/accounts").json()
    assert listed[0]["health_status"] == "expired"

    updated = client.put(
        "/api/accounts/buyer",
        json={"content": '{"cookies": [{"name": "a", "value": "b"}]}'},
    )
    assert updated.status_code == 200
    assert client.get("/api/accounts").json()[0]["health_status"] == "unknown"


def test_manual_health_check_rejects_parallel_and_returns_result(monkeypatch, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "buyer.json").write_text('{"cookies": []}', encoding="utf-8")
    monkeypatch.setenv("ACCOUNT_STATE_DIR", str(state_dir))
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))

    async def fake_check(path):
        return {"status": "available", "message": "ok"}

    monkeypatch.setattr(accounts, "check_account_health", fake_check)
    response = _client().post("/api/accounts/buyer/health-check")
    assert response.status_code == 200
    assert response.json()["health_status"] == "available"
    assert response.json()["health_source"] == "manual"


def test_manual_health_check_returns_409_when_same_account_is_running(monkeypatch, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "buyer.json").write_text('{"cookies": []}', encoding="utf-8")
    monkeypatch.setenv("ACCOUNT_STATE_DIR", str(state_dir))

    class BusyLock:
        def locked(self):
            return True

    monkeypatch.setitem(accounts._health_check_locks, "buyer", BusyLock())
    response = _client().post("/api/accounts/buyer/health-check")

    assert response.status_code == 409
