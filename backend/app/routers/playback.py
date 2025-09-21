from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..services.playback import upsert_playback_state


router = APIRouter(prefix="/rooms", tags=["playback"])


@router.get("/{room_id}/playback", response_model=schemas.PlaybackStateRead)
def get_playback(room_id: str, session: Session = Depends(get_session)):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room.playback_state:
        raise HTTPException(status_code=404, detail="Playback state not initialized")
    return room.playback_state


@router.put("/{room_id}/playback", response_model=schemas.PlaybackStateRead)
def set_playback(
    room_id: str,
    payload: schemas.PlaybackStateUpdate,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    track = session.get(models.Track, payload.track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    state = upsert_playback_state(
        session=session,
        room=room,
        track=track,
        start_ts=payload.start_ts,
        offset_ms=payload.offset_ms,
        is_paused=payload.is_paused,
        listeners=payload.listeners,
    )
    room.live_track_id = track.id
    session.add(room)
    session.commit()
    session.refresh(state)
    return state
