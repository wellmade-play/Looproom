from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyTokenRefreshError(RuntimeError):
    """Raised when refreshing a Spotify access token fails."""


def ensure_valid_access_token(session: Session, user: models.User) -> Tuple[str, int]:
    """Return a valid Spotify access token for the user, refreshing when needed."""

    now = datetime.now(timezone.utc)
    expires_at_raw = user.token_expires_at
    expires_at = None
    if isinstance(expires_at_raw, datetime):
        expires_at = expires_at_raw
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            user.token_expires_at = expires_at
    elif isinstance(expires_at_raw, str) and expires_at_raw:
        try:
            parsed = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            expires_at = parsed
            user.token_expires_at = parsed
    if expires_at and expires_at - timedelta(seconds=120) > now:
        remaining = int((expires_at - now).total_seconds())
        return user.access_token, max(remaining, 0)

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SpotifyTokenRefreshError("Spotify client credentials are not configured")
    if not user.refresh_token:
        raise SpotifyTokenRefreshError("Spotify refresh token is missing for this user")

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": user.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = httpx.post(SPOTIFY_TOKEN_URL, data=payload, timeout=15.0)
    except httpx.HTTPError as exc:  # pragma: no cover - network errors
        logger.exception("Failed to refresh Spotify token for user %s", user.id)
        raise SpotifyTokenRefreshError("Failed to call Spotify token endpoint") from exc

    if response.status_code != 200:
        logger.error(
            "Spotify token refresh failed for user %s: %s", user.id, response.text
        )
        raise SpotifyTokenRefreshError("Spotify token refresh failed")

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise SpotifyTokenRefreshError("Spotify response missing access_token")

    expires_in = int(data.get("expires_in", 3600))
    scope = data.get("scope")
    user.access_token = access_token
    user.token_expires_at = now + timedelta(seconds=expires_in)
    if scope:
        user.scope = scope
    session.add(user)
    session.flush()

    return access_token, expires_in
