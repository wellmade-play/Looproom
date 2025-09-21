from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session


router = APIRouter(prefix="/artists", tags=["artists"])


@router.post("", response_model=schemas.ArtistRead, status_code=201)
def create_artist(*args, **kwargs):
    raise HTTPException(status_code=403, detail="Artist creation is managed via Spotify sync")


@router.get("", response_model=list[schemas.ArtistRead])
def list_artists(session: Session = Depends(get_session)):
    artists = session.scalars(
        select(models.Artist).order_by(models.Artist.popularity.desc(), models.Artist.followers.desc(), models.Artist.name)
    )
    return list(artists)


@router.get("/{artist_id}", response_model=schemas.ArtistRead)
def get_artist(artist_id: str, session: Session = Depends(get_session)):
    artist = session.get(models.Artist, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist

