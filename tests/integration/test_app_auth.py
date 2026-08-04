import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.app import app
from src.infrastructure.config.settings import settings as app_settings


def test_business_api_requires_login_and_accepts_signed_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("ACCOUNT_STATE_DIR", str(tmp_path / "state"))
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/accounts").status_code == 401
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 4401

    login = client.post(
        "/auth/status",
        json={
            "username": app_settings.web_username,
            "password": app_settings.web_password,
        },
    )
    assert login.status_code == 200
    assert client.get("/api/accounts").status_code == 200
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("ping")

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/api/accounts").status_code == 401
