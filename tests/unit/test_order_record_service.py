from concurrent.futures import ThreadPoolExecutor

from src.services.order_record_service import (
    get_order_record,
    reserve_order_record,
    update_order_record,
)


def _reservation():
    return reserve_order_record(
        task_id=1,
        task_name="camera",
        account_name="buyer",
        account_path="state/buyer.json",
        result_filename="a7m4_full_data.jsonl",
        item_id="1001",
        title="A7M4",
        item_link="https://www.goofish.com/item?id=1001",
        value_score=90,
        score_threshold=85,
        observed_price=7000,
        max_price=8000,
    )


def test_order_reservation_is_idempotent_across_threads(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(lambda _: _reservation(), range(2)))
    assert sum(record is not None for record in records) == 1


def test_submitted_order_cannot_be_prepared_for_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    record = _reservation()
    update_order_record(record["id"], status="submitted_unpaid", platform_order_id="O-1")
    stored = get_order_record(record["id"])
    assert stored["status"] == "submitted_unpaid"
    assert _reservation() is None
