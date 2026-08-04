"""Persistent account health state shared by the API and scraper processes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.infrastructure.persistence.sqlite_connection import init_schema, sqlite_connection


ACCOUNT_HEALTH_STATUSES = {
    "unknown",
    "available",
    "expired",
    "risk_controlled",
    "invalid_file",
    "error",
}
RISK_CONTROL_COOLDOWN = timedelta(minutes=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def account_name_from_path(account_path: str) -> str:
    return Path(account_path).stem


def _default_payload(account_path: str) -> dict:
    return {
        "health_status": "unknown",
        "health_source": None,
        "last_checked_at": None,
        "last_success_at": None,
        "health_message": None,
        "account_path": account_path,
    }


def get_account_health(account_path: str) -> dict:
    account_name = account_name_from_path(account_path)
    with sqlite_connection() as conn:
        init_schema(conn)
        row = conn.execute(
            "SELECT * FROM account_health WHERE account_name = ?",
            (account_name,),
        ).fetchone()
    if row is None:
        return _default_payload(account_path)
    return {
        "health_status": row["status"],
        "health_source": row["source"],
        "last_checked_at": row["last_checked_at"],
        "last_success_at": row["last_success_at"],
        "health_message": row["message"],
        "account_path": row["account_path"],
    }


def record_account_health(
    account_path: str,
    status: str,
    *,
    source: str,
    message: str | None = None,
    checked_at: datetime | None = None,
    clear_success: bool = False,
) -> dict:
    if status not in ACCOUNT_HEALTH_STATUSES:
        raise ValueError(f"不支持的账号健康状态: {status}")
    current = checked_at or _utcnow()
    account_name = account_name_from_path(account_path)
    existing = get_account_health(account_path)
    last_success_at = (
        None
        if clear_success
        else (_iso(current) if status == "available" else existing["last_success_at"])
    )
    with sqlite_connection() as conn:
        init_schema(conn)
        conn.execute(
            """
            INSERT INTO account_health (
                account_name, account_path, status, source, last_checked_at,
                last_success_at, message, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_name) DO UPDATE SET
                account_path = excluded.account_path,
                status = excluded.status,
                source = excluded.source,
                last_checked_at = excluded.last_checked_at,
                last_success_at = excluded.last_success_at,
                message = excluded.message,
                updated_at = excluded.updated_at
            """,
            (
                account_name,
                account_path,
                status,
                source,
                _iso(current),
                last_success_at,
                (message or "")[:1000] or None,
                _iso(current),
            ),
        )
        conn.commit()
    return get_account_health(account_path)


def reset_account_health(account_path: str) -> dict:
    return record_account_health(
        account_path,
        "unknown",
        source="account_update",
        message="登录态已更新，等待重新检测。",
        clear_success=True,
    )


def delete_account_health(account_path: str) -> None:
    with sqlite_connection() as conn:
        init_schema(conn)
        conn.execute(
            "DELETE FROM account_health WHERE account_name = ?",
            (account_name_from_path(account_path),),
        )
        conn.commit()


def is_account_eligible(
    account_path: str,
    *,
    now: datetime | None = None,
) -> bool:
    health = get_account_health(account_path)
    status = health["health_status"]
    if status in {"expired", "invalid_file"}:
        return False
    if status != "risk_controlled":
        return True
    checked_at = _parse_datetime(health["last_checked_at"])
    return checked_at is None or (now or _utcnow()) - checked_at >= RISK_CONTROL_COOLDOWN


def filter_eligible_account_files(
    account_paths: list[str],
    *,
    now: datetime | None = None,
) -> list[str]:
    return [path for path in account_paths if is_account_eligible(path, now=now)]
