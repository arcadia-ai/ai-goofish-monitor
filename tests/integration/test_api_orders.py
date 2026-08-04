from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import orders
from src.api.session_auth import SESSION_COOKIE_NAME, create_session_token
from src.services.order_record_service import reserve_order_record, update_order_record


def _client(*, authenticated=True):
    app = FastAPI()
    app.include_router(orders.router)
    client = TestClient(app)
    if authenticated:
        client.cookies.set(SESSION_COOKIE_NAME, create_session_token())
    return client


def _reserve():
    return reserve_order_record(
        task_id=1,
        task_name="测试任务",
        account_name="buyer",
        account_path="state/buyer.json",
        result_filename="demo_full_data.jsonl",
        item_id="1001",
        title="测试商品",
        item_link="https://www.goofish.com/item?id=1001",
        value_score=90,
        score_threshold=85,
        observed_price=88,
        max_price=100,
    )


def test_order_list_and_retry_state_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    record = _reserve()
    client = _client()

    listed = client.get("/api/orders")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    disabled = client.post(f"/api/orders/{record['id']}/retry")
    assert disabled.status_code == 409

    monkeypatch.setenv("AUTO_ORDER_MASTER_ENABLED", "true")
    update_order_record(record["id"], status="submitted_unpaid")
    submitted = client.post(f"/api/orders/{record['id']}/retry")
    assert submitted.status_code == 409


def test_unconfirmed_submission_cannot_be_retried(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    monkeypatch.setenv("AUTO_ORDER_MASTER_ENABLED", "true")
    record = _reserve()
    update_order_record(
        record["id"], status="submitting", reason="submission_unconfirmed"
    )

    response = _client().post(f"/api/orders/{record['id']}/retry")

    assert response.status_code == 409


def test_order_api_requires_authenticated_session(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    assert _client(authenticated=False).get("/api/orders").status_code == 401


def test_failed_order_can_be_manually_retried(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    monkeypatch.setenv("AUTO_ORDER_MASTER_ENABLED", "true")
    record = _reserve()
    failed = update_order_record(record["id"], status="failed", reason="safe_stop")

    async def fake_retry(_record):
        return {**failed, "status": "submitted_unpaid", "platform_order_id": "ORDER-2"}

    monkeypatch.setattr(orders, "retry_order_record", fake_retry)
    response = _client().post(f"/api/orders/{record['id']}/retry")
    assert response.status_code == 200
    assert response.json()["order"]["status"] == "submitted_unpaid"
