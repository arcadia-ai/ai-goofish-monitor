"""Signed same-site session used by sensitive order APIs."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request, Response

from src.infrastructure.config.settings import settings as app_settings


SESSION_COOKIE_NAME = "goofish_session"
SESSION_TTL_SECONDS = 12 * 60 * 60


def _signature(payload: str) -> str:
    return hmac.new(
        app_settings.web_password.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(*, now: int | None = None) -> str:
    issued_at = now if now is not None else int(time.time())
    payload = f"{app_settings.web_username}:{issued_at}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{_signature(payload)}"


def _decode_session_token(token: str) -> tuple[str, int] | None:
    try:
        encoded, signature = token.split(".", 1)
        padding = "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        if not hmac.compare_digest(signature, _signature(payload)):
            return None
        username, timestamp = payload.rsplit(":", 1)
        return username, int(timestamp)
    except (ValueError, UnicodeError):
        return None


def is_authenticated_session(token: str, *, now: int | None = None) -> bool:
    parsed = _decode_session_token(token)
    if parsed is None:
        return False
    username, issued_at = parsed
    current = now if now is not None else int(time.time())
    age = current - issued_at
    return (
        username == app_settings.web_username
        and age >= -60
        and age <= SESSION_TTL_SECONDS
    )


def set_session_cookie(response: Response, request: Request) -> None:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or forwarded_proto == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="strict")


async def require_authenticated_session(request: Request) -> None:
    if not is_authenticated_session(
        request.cookies.get(SESSION_COOKIE_NAME, "")
    ):
        raise HTTPException(status_code=401, detail="登录会话无效或已过期。")
