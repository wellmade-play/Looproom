from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..security import get_current_user
from ..services.spotify_oauth import (
    SpotifyTokenRefreshError,
    ensure_valid_access_token,
)

router = APIRouter(prefix="/spotify", tags=["spotify"])


@router.get("/playback-token", response_model=schemas.SpotifyPlaybackToken)
def playback_token(
    session: Session = Depends(get_session),
    user: models.User = Depends(get_current_user),
) -> schemas.SpotifyPlaybackToken:
    try:
        access_token, expires_in = ensure_valid_access_token(session, user)
        session.commit()
    except SpotifyTokenRefreshError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.SpotifyPlaybackToken(access_token=access_token, expires_in=expires_in)
