from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session


router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.post("", response_model=schemas.TrackRead, status_code=201)
def create_track(*args, **kwargs):
    raise HTTPException(status_code=403, detail="Track creation is managed via Spotify sync")


@router.get("", response_model=list[schemas.TrackRead])
def list_tracks(
    artist_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    stmt = select(models.Track)
    if artist_id:
        stmt = stmt.where(models.Track.artist_id == artist_id)
    stmt = stmt.order_by(models.Track.popularity.desc(), models.Track.created_at.desc())
    tracks = session.scalars(stmt)
    return list(tracks)


@router.get("/{track_id}", response_model=schemas.TrackRead)
def get_track(track_id: str, session: Session = Depends(get_session)):
    track = session.get(models.Track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track
