from __future__ import annotations

import copy
from datetime import datetime, timedelta

from src.failure_guard import FailureGuard


class InMemoryFailureGuard(FailureGuard):
    def __init__(self, data: dict, **kwargs):
        super().__init__(path="in-memory-guard.json", **kwargs)
        self.data = data

    def _load(self) -> dict:
        return copy.deepcopy(self.data)

    def _save(self, data: dict) -> None:
        self.data = copy.deepcopy(data)


def test_failure_guard_opens_circuit_after_threshold_and_rate_limits(tmp_path):
    guard_path = tmp_path / "guard.json"
    cookie_path = tmp_path / "xianyu_state.json"
    cookie_path.write_text("{}", encoding="utf-8")

    guard = FailureGuard(
        path=str(guard_path),
        threshold=3,
        pause_seconds=3 * 24 * 60 * 60,
        tz_name="Asia/Shanghai",
    )

    base = datetime(2026, 3, 4, 12, 0, 0)

    r1 = guard.record_failure("task-a", "err-1", cookie_path=str(cookie_path), now=base)
    assert r1["should_notify"] is False
    assert r1["opened_circuit"] is False

    r2 = guard.record_failure("task-a", "err-2", cookie_path=str(cookie_path), now=base)
    assert r2["should_notify"] is False
    assert r2["opened_circuit"] is False

    r3 = guard.record_failure("task-a", "err-3", cookie_path=str(cookie_path), now=base)
    assert r3["should_notify"] is True
    assert r3["opened_circuit"] is True
    assert r3["paused_until"] is not None

    d0 = guard.should_skip_start("task-a", cookie_path=str(cookie_path), now=base)
    assert d0.skip is True
    assert d0.should_notify is False

    next_day = base + timedelta(days=1, minutes=1)
    d1 = guard.should_skip_start("task-a", cookie_path=str(cookie_path), now=next_day)
    assert d1.skip is True
    assert d1.should_notify is True

    d1b = guard.should_skip_start("task-a", cookie_path=str(cookie_path), now=next_day)
    assert d1b.skip is True
    assert d1b.should_notify is False


def test_failure_guard_auto_recovers_on_cookie_change(tmp_path):
    guard_path = tmp_path / "guard.json"
    cookie_path = tmp_path / "xianyu_state.json"
    cookie_path.write_text("{}", encoding="utf-8")

    guard = FailureGuard(
        path=str(guard_path),
        threshold=2,
        pause_seconds=3 * 24 * 60 * 60,
        tz_name="Asia/Shanghai",
    )

    base = datetime(2026, 3, 4, 12, 0, 0)

    guard.record_failure("task-a", "err-1", cookie_path=str(cookie_path), now=base)
    guard.record_failure("task-a", "err-2", cookie_path=str(cookie_path), now=base)

    paused = guard.should_skip_start("task-a", cookie_path=str(cookie_path), now=base)
    assert paused.skip is True

    cookie_path.write_text('{"updated": true}', encoding="utf-8")

    recovered = guard.should_skip_start(
        "task-a",
        cookie_path=str(cookie_path),
        now=base + timedelta(minutes=1),
    )
    assert recovered.skip is False


def test_release_for_cookie_path_only_resets_related_tasks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    account_path = tmp_path / "state" / "buyer.json"
    account_path.parent.mkdir()
    account_path.write_text("{}", encoding="utf-8")
    failed_at = "2026-08-04T11:46:22+08:00"
    success_at = "2026-08-04T11:00:56+08:00"
    data = {
        "version": 1,
        "tasks": {
            "task-a": {
                "consecutive_failures": 3,
                "paused_until": "2026-08-05T11:46:22+08:00",
                "last_notified_date": "2026-08-05",
                "last_failure_reason": "old timeout",
                "last_failure_at": failed_at,
                "last_success_at": success_at,
                "cookie_path": "state/buyer.json",
            },
            "task-b": {
                "consecutive_failures": 3,
                "paused_until": "2026-08-05T11:46:22+08:00",
                "last_failure_reason": "other account",
                "cookie_path": "state/other.json",
            },
        },
    }
    guard = InMemoryFailureGuard(data, tz_name="Asia/Shanghai")
    recovered_at = datetime(2026, 8, 5, 11, 16, 36)

    released = guard.release_for_cookie_path(
        str(account_path),
        now=recovered_at,
    )

    assert released == ["task-a"]
    entry = guard.data["tasks"]["task-a"]
    assert entry["consecutive_failures"] == 0
    assert entry["paused_until"] is None
    assert entry["last_notified_date"] is None
    assert entry["last_failure_reason"] == "old timeout"
    assert entry["last_failure_at"] == failed_at
    assert entry["last_success_at"] == success_at
    assert entry["last_recovered_at"] == recovered_at.isoformat()
    assert entry["last_recovery_reason"] == "account_health_available"
    assert guard.data["tasks"]["task-b"] == data["tasks"]["task-b"]


def test_release_for_cookie_path_ignores_clean_or_unrelated_tasks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    data = {
        "version": 1,
        "tasks": {
            "clean": {
                "consecutive_failures": 0,
                "paused_until": None,
                "cookie_path": "state/buyer.json",
            },
            "other": {
                "consecutive_failures": 2,
                "paused_until": None,
                "cookie_path": "state/other.json",
            },
        },
    }
    guard = InMemoryFailureGuard(data)

    released = guard.release_for_cookie_path(str(tmp_path / "state" / "buyer.json"))

    assert released == []
    assert guard.data == data
