"""SQLite persistence for auditable automatic order attempts."""
from __future__ import annotations

from datetime import datetime, timezone

from src.infrastructure.persistence.sqlite_connection import init_schema, sqlite_connection


ORDER_STATUSES = {
    "queued",
    "submitting",
    "submitted_unpaid",
    "blocked",
    "failed",
    "skipped",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def reserve_order_record(**values) -> dict | None:
    current = _now()
    with sqlite_connection() as conn:
        init_schema(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO order_records (
                task_id, task_name, account_name, account_path, result_filename,
                item_id, title, item_link, value_score, score_threshold,
                observed_price, max_price, status, attempt_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)
            """,
            (
                values.get("task_id"),
                values["task_name"],
                values["account_name"],
                values["account_path"],
                values.get("result_filename"),
                values["item_id"],
                values.get("title"),
                values.get("item_link"),
                float(values["value_score"]),
                float(values["score_threshold"]),
                float(values["observed_price"]),
                float(values["max_price"]),
                current,
                current,
            ),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None
        record_id = cursor.lastrowid
    return get_order_record(record_id)


def get_order_record(record_id: int) -> dict | None:
    with sqlite_connection() as conn:
        init_schema(conn)
        row = conn.execute(
            "SELECT * FROM order_records WHERE id = ?", (record_id,)
        ).fetchone()
    return _row_dict(row)


def find_order_record(account_name: str, item_id: str) -> dict | None:
    with sqlite_connection() as conn:
        init_schema(conn)
        row = conn.execute(
            "SELECT * FROM order_records WHERE account_name = ? AND item_id = ?",
            (account_name, item_id),
        ).fetchone()
    return _row_dict(row)


def update_order_record(
    record_id: int,
    *,
    status: str,
    reason: str | None = None,
    payable_total: float | None = None,
    platform_order_id: str | None = None,
    increment_attempt: bool = False,
) -> dict:
    if status not in ORDER_STATUSES:
        raise ValueError(f"不支持的锁单状态: {status}")
    current = _now()
    submitted_at = current if status == "submitted_unpaid" else None
    with sqlite_connection() as conn:
        init_schema(conn)
        cursor = conn.execute(
            """
            UPDATE order_records
            SET status = ?, reason = ?, payable_total = COALESCE(?, payable_total),
                platform_order_id = COALESCE(?, platform_order_id),
                attempt_count = attempt_count + ?, updated_at = ?,
                submitted_at = COALESCE(?, submitted_at)
            WHERE id = ?
            """,
            (
                status,
                (reason or "")[:1000] or None,
                payable_total,
                platform_order_id,
                1 if increment_attempt else 0,
                current,
                submitted_at,
                record_id,
            ),
        )
        conn.commit()
        if cursor.rowcount != 1:
            raise KeyError(record_id)
    return get_order_record(record_id)


def list_order_records(
    *,
    status: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict], int]:
    conditions = []
    params: list[object] = []
    if status:
        if status not in ORDER_STATUSES:
            raise ValueError("无效的锁单状态")
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with sqlite_connection() as conn:
        init_schema(conn)
        total = conn.execute(
            f"SELECT COUNT(*) FROM order_records {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM order_records {where} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    return [dict(row) for row in rows], int(total)


def prepare_manual_retry(record_id: int) -> dict | None:
    current = _now()
    with sqlite_connection() as conn:
        init_schema(conn)
        cursor = conn.execute(
            """
            UPDATE order_records
            SET status = 'queued', reason = NULL, updated_at = ?
            WHERE id = ? AND status IN ('blocked', 'failed', 'skipped')
            """,
            (current, record_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None
    return get_order_record(record_id)
