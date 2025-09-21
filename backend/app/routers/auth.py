from __future__ import annotations

import logging

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..security import clear_session_cookie, create_session_token, set_session_cookie

logger = logging.getLogger(__name__)

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_ME_URL = "https://api.spotify.com/v1/me"
DEFAULT_SCOPES = os.getenv(
    "SPOTIFY_SCOPES",
    "user-read-email user-read-private user-read-playback-state user-modify-playback-state",
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_credentials() -> tuple[str, str]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set"
        )
    return client_id, client_secret


def _resolve_redirect_uri(request: Request) -> str:
    env_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    if env_uri:
        return env_uri.rstrip("/")
    return str(request.url_for("spotify_callback"))


@router.get("/spotify/login", response_model=schemas.SpotifyLoginResponse)
def spotify_login(
    request: Request,
    redirect_uri: Optional[str] = None,
    session: Session = Depends(get_session),
):
    client_id, _ = _client_credentials()
    callback_uri = _resolve_redirect_uri(request)

    # Clean up expired auth states (older than 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    session.execute(
        delete(models.SpotifyAuthState).where(models.SpotifyAuthState.created_at < cutoff)
    )

    state = secrets.token_urlsafe(32)
    auth_state = models.SpotifyAuthState(state=state, redirect_uri=redirect_uri)
    session.add(auth_state)
    session.commit()

    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback_uri,
            "scope": DEFAULT_SCOPES,
            "state": state,
            "show_dialog": os.getenv("SPOTIFY_FORCE_DIALOG", "false"),
        }
    )
    return schemas.SpotifyLoginResponse(auth_url=f"{SPOTIFY_AUTHORIZE_URL}?{query}")


@router.get("/spotify/callback", name="spotify_callback")
async def spotify_callback(
    request: Request,
    code: str,
    state: str,
    session: Session = Depends(get_session),
):
    logger.info("Handling Spotify callback: state=%s", state)
    client_id, client_secret = _client_credentials()
    callback_uri = _resolve_redirect_uri(request)

    auth_state = session.scalar(
        select(models.SpotifyAuthState).where(models.SpotifyAuthState.state == state)
    )
    if not auth_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    redirect_target = auth_state.redirect_uri or "/"
    session.delete(auth_state)
    session.commit()

    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if token_res.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token exchange failed")

    token_data = token_res.json()
    access_token: str = token_data.get("access_token")
    refresh_token: Optional[str] = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in", 3600))
    scope = token_data.get("scope")

    async with httpx.AsyncClient(timeout=10) as client:
        me_res = await client.get(
            SPOTIFY_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if me_res.status_code != 200:
        logger.error("Spotify profile fetch failed: status=%s body=%s", me_res.status_code, me_res.text)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load profile")

    profile = me_res.json()
    spotify_id = profile.get("id")
    if not spotify_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spotify profile missing id")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    avatar_url: Optional[str] = None
    images = profile.get("images")
    if isinstance(images, list) and images:
        first_image = images[0]
        if isinstance(first_image, dict):
            avatar_url = first_image.get("url")

    user = session.scalar(
        select(models.User).where(models.User.spotify_id == spotify_id)
    )
    if user is None:
        if refresh_token is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh token")
        user = models.User(
            spotify_id=spotify_id,
            display_name=profile.get("display_name") or spotify_id,
            avatar_url=avatar_url,
            email=profile.get("email"),
            country=profile.get("country"),
            product=profile.get("product"),
            access_token=access_token,
            refresh_token=refresh_token or "",
            token_expires_at=expires_at,
            scope=scope,
            preferences={},
        )
        session.add(user)
    else:
        user.display_name = profile.get("display_name") or user.display_name
        user.avatar_url = avatar_url or user.avatar_url
        user.email = profile.get("email") or user.email
        user.country = profile.get("country") or user.country
        user.product = profile.get("product") or user.product
        user.access_token = access_token
        if refresh_token:
            user.refresh_token = refresh_token
        user.token_expires_at = expires_at
        user.scope = scope or user.scope

    session.commit()

    session_token = create_session_token(user.id)
    logger.info("Spotify login success for user %s; redirecting to %s", user.spotify_id, redirect_target)
    redirect_response = RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(redirect_response, session_token, request=request)
    return redirect_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(request: Request) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, request=request)
    logger.info("User logged out")
    return response




