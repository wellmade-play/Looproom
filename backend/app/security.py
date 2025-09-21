from __future__ import annotations

import os
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from . import models
from .database import get_session

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "looproom_session")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "2592000"))  # 30 days default
_raw_secure = os.getenv("SESSION_COOKIE_SECURE")
SESSION_COOKIE_SECURE_CONFIG: Optional[bool]
if _raw_secure is None or _raw_secure.lower() == "auto":
    SESSION_COOKIE_SECURE_CONFIG = None
else:
    SESSION_COOKIE_SECURE_CONFIG = _raw_secure.lower() in {"1", "true", "yes", "on"}
SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN")
SESSION_COOKIE_SAMESITE_OVERRIDE = os.getenv("SESSION_COOKIE_SAMESITE")


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("APP_SECRET")
    if not secret:
        raise RuntimeError("APP_SECRET environment variable is required for session management")
    return URLSafeTimedSerializer(secret_key=secret, salt="looproom.session")


def _is_https(request: Request | None) -> bool:
    if request is None:
        return False
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        proto = forwarded.split(",")[0].strip().lower()
        return proto == "https"
    return request.url.scheme == "https"


def _should_secure(request: Request | None) -> bool:
    if SESSION_COOKIE_SECURE_CONFIG is not None:
        return SESSION_COOKIE_SECURE_CONFIG
    return _is_https(request)


def _cookie_samesite(secure: bool) -> str:
    if SESSION_COOKIE_SAMESITE_OVERRIDE:
        return SESSION_COOKIE_SAMESITE_OVERRIDE
    return "none" if secure else "lax"


def create_session_token(user_id: str) -> str:
    return _serializer().dumps({"sub": user_id})


def verify_session_token(token: str) -> str:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except SignatureExpired as exc:  # pragma: no cover - fast fail
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired") from exc
    except BadSignature as exc:  # pragma: no cover - fast fail
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    user_id = data.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")
    return user_id


def set_session_cookie(response, token: str, request: Request | None = None) -> None:
    secure_flag = _should_secure(request)
    samesite = _cookie_samesite(secure_flag)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_flag,
        samesite=samesite,
        path="/",
        domain=SESSION_COOKIE_DOMAIN,
    )


def clear_session_cookie(response, request: Request | None = None) -> None:
    secure_flag = _should_secure(request)
    samesite = _cookie_samesite(secure_flag)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        "",
        max_age=0,
        expires=0,
        httponly=True,
        secure=secure_flag,
        samesite=samesite,
        path="/",
        domain=SESSION_COOKIE_DOMAIN,
    )


def get_session_token(session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> str:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session_token


def get_current_user(
    session: Session = Depends(get_session),
    session_token: str = Depends(get_session_token),
) -> models.User:
    user_id = verify_session_token(session_token)
    user = session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
