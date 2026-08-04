from datetime import datetime, timedelta, timezone

from src.services.account_health_service import (
    filter_eligible_account_files,
    get_account_health,
    record_account_health,
    reset_account_health,
)


def test_account_health_persists_and_resets(monkeypatch, tmp_path):
    db_path = tmp_path / "app.sqlite3"
    monkeypatch.setenv("APP_DATABASE_FILE", str(db_path))
    account = tmp_path / "state" / "buyer.json"
    account.parent.mkdir()
    account.write_text("{}", encoding="utf-8")

    record_account_health(
        str(account),
        "available",
        source="task",
        message="authenticated search succeeded",
        checked_at=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
    )
    health = get_account_health(str(account))
    assert health["health_status"] == "available"
    assert health["health_source"] == "task"
    assert health["last_success_at"] is not None

    reset_account_health(str(account))
    reset = get_account_health(str(account))
    assert reset["health_status"] == "unknown"
    assert reset["last_success_at"] is None


def test_account_health_filters_expired_invalid_and_risk_cooldown(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    available = state_dir / "available.json"
    expired = state_dir / "expired.json"
    invalid = state_dir / "invalid.json"
    cooling = state_dir / "cooling.json"
    cooled = state_dir / "cooled.json"
    for path in (available, expired, invalid, cooling, cooled):
        path.write_text("{}", encoding="utf-8")

    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    record_account_health(str(available), "available", source="task", checked_at=now)
    record_account_health(str(expired), "expired", source="task", checked_at=now)
    record_account_health(str(invalid), "invalid_file", source="task", checked_at=now)
    record_account_health(str(cooling), "risk_controlled", source="task", checked_at=now)
    record_account_health(
        str(cooled),
        "risk_controlled",
        source="task",
        checked_at=now - timedelta(minutes=31),
    )

    filtered = filter_eligible_account_files(
        [str(path) for path in (available, expired, invalid, cooling, cooled)],
        now=now,
    )
    assert filtered == [str(available), str(cooled)]
