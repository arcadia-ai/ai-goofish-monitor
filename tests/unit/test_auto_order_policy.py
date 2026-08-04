import sqlite3

import pytest
from pydantic import ValidationError

from src.domain.models.task import TaskCreate
from src.infrastructure.persistence.sqlite_connection import init_schema
from src.services.auto_order_policy import evaluate_auto_order


def _task_payload(**overrides):
    payload = {
        "task_name": "camera",
        "keyword": "a7m4",
        "description": "个人卖家且成色良好",
        "decision_mode": "ai",
        "account_strategy": "fixed",
        "account_state_file": "state/buyer.json",
        "auto_order_enabled": True,
        "auto_order_score_threshold": 85,
        "auto_order_max_price": "8000",
        "auto_order_max_per_run": 1,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"decision_mode": "keyword", "keyword_rules": ["a7m4"]},
        {"account_strategy": "auto", "account_state_file": None},
        {"auto_order_max_price": None},
        {"auto_order_max_price": "0"},
        {"auto_order_score_threshold": 101},
        {"auto_order_max_per_run": 6},
    ],
)
def test_auto_order_task_requires_safe_configuration(overrides):
    with pytest.raises(ValidationError):
        TaskCreate(**_task_payload(**overrides))


def test_auto_order_task_defaults_to_disabled():
    task = TaskCreate(
        task_name="camera",
        keyword="a7m4",
        description="成色良好",
    )
    assert task.auto_order_enabled is False
    assert task.auto_order_score_threshold == 85
    assert task.auto_order_max_per_run == 1
    assert task.auto_order_max_price is None


def test_auto_order_policy_requires_recommendation_score_and_price():
    task = TaskCreate(**_task_payload())
    allowed = evaluate_auto_order(
        task.model_dump(),
        {"is_recommended": True, "value_score": 90},
        {"商品ID": "1001", "当前售价": "7999"},
        master_enabled=True,
        attempts_in_run=0,
    )
    assert allowed.eligible is True

    missing_score = evaluate_auto_order(
        task.model_dump(),
        {"is_recommended": True},
        {"商品ID": "1001", "当前售价": "7999"},
        master_enabled=True,
        attempts_in_run=0,
    )
    assert missing_score.eligible is False
    assert missing_score.reason == "missing_value_score"

    too_expensive = evaluate_auto_order(
        task.model_dump(),
        {"is_recommended": True, "value_score": 90},
        {"商品ID": "1001", "当前售价": "8001"},
        master_enabled=True,
        attempts_in_run=0,
    )
    assert too_expensive.eligible is False
    assert too_expensive.reason == "price_above_limit"

    invalid_price = evaluate_auto_order(
        task.model_dump(),
        {"is_recommended": True, "value_score": 90},
        {"商品ID": "1001", "当前售价": "0"},
        master_enabled=True,
        attempts_in_run=0,
    )
    assert invalid_price.eligible is False
    assert invalid_price.reason == "invalid_item_price"


def test_schema_contains_auto_order_defaults_and_new_tables():
    conn = sqlite3.connect(":memory:")
    init_schema(conn)

    task_columns = {
        row[1]: row for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    assert task_columns["auto_order_enabled"][4] == "0"
    assert task_columns["auto_order_score_threshold"][4] == "85"
    assert task_columns["auto_order_max_per_run"][4] == "1"

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"account_health", "order_records"}.issubset(tables)


def test_schema_migrates_existing_tasks_without_changing_old_rows():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY, task_name TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO tasks (id, task_name) VALUES (7, 'legacy')")

    init_schema(conn)

    row = conn.execute(
        """
        SELECT task_name, auto_order_enabled, auto_order_score_threshold,
               auto_order_max_price, auto_order_max_per_run
        FROM tasks WHERE id = 7
        """
    ).fetchone()
    assert row == ("legacy", 0, 85, None, 1)
