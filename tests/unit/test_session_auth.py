from src.api.session_auth import (
    SESSION_TTL_SECONDS,
    _decode_session_token,
    create_session_token,
    is_authenticated_session,
)
from src.infrastructure.config.settings import settings as app_settings


def test_signed_session_token_rejects_tampering():
    token = create_session_token(now=0)
    assert _decode_session_token(token) == (app_settings.web_username, 0)
    assert _decode_session_token(f"{token}x") is None
    assert is_authenticated_session(token, now=SESSION_TTL_SECONDS)
    assert not is_authenticated_session(token, now=SESSION_TTL_SECONDS + 1)
