from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..services.playback import (
    pause_room_playback,
    resume_room_playback,
    update_room_listener_count,
)


router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=schemas.RoomRead, status_code=201)
def create_room(payload: schemas.RoomCreate, session: Session = Depends(get_session)):
    artist = session.get(models.Artist, payload.artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    room = models.Room(**payload.model_dump())
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.get("", response_model=list[schemas.RoomRead])
def list_rooms(
    artist_id: str | None = Query(default=None),
    mode: models.RoomMode | None = Query(default=None),
    featured: bool | None = Query(default=None),
    session: Session = Depends(get_session),
):
    stmt = select(models.Room)
    if artist_id:
        stmt = stmt.where(models.Room.artist_id == artist_id)
    if mode:
        stmt = stmt.where(models.Room.mode == mode)
    if featured is not None:
        stmt = stmt.where(models.Room.is_featured.is_(featured))
    stmt = stmt.order_by(models.Room.created_at.desc())
    rooms = session.scalars(stmt)
    return list(rooms)


@router.get("/{room_id}", response_model=schemas.RoomRead)
def get_room(room_id: str, session: Session = Depends(get_session)):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.patch("/{room_id}", response_model=schemas.RoomRead)
def update_room(
    room_id: str, payload: schemas.RoomUpdate, session: Session = Depends(get_session)
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(room, key, value)

    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.post("/{room_id}/join", response_model=schemas.MembershipRead, status_code=201)
def join_room(
    room_id: str,
    payload: schemas.RoomJoinRequest,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    user = session.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    membership = session.scalar(
        select(models.RoomMembership).where(
            models.RoomMembership.room_id == room_id,
            models.RoomMembership.user_id == payload.user_id,
        )
    )

    if membership:
        membership.left_at = None
        membership.role = payload.role
    else:
        membership = models.RoomMembership(
            room_id=room_id,
            user_id=payload.user_id,
            role=payload.role,
            joined_at=datetime.utcnow(),
        )

    session.add(membership)
    session.flush()
    listeners = update_room_listener_count(session, room)
    if listeners > 0:
        resume_room_playback(session, room, listeners)
    session.commit()
    session.refresh(membership)
    return membership


@router.post("/{room_id}/leave", response_model=schemas.MembershipRead)
def leave_room(
    room_id: str,
    payload: schemas.RoomLeaveRequest,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = session.scalar(
        select(models.RoomMembership).where(
            models.RoomMembership.room_id == room_id,
            models.RoomMembership.user_id == payload.user_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    membership.left_at = datetime.utcnow()
    session.add(membership)
    session.flush()
    listeners = update_room_listener_count(session, room)
    if listeners == 0:
        pause_room_playback(session, room, listeners)
    else:
        resume_room_playback(session, room, listeners)
    session.commit()
    session.refresh(membership)
    return membership


@router.get("/{room_id}/queue", response_model=list[schemas.QueueEntryRead])
def get_queue(room_id: str, session: Session = Depends(get_session)):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    entries = session.scalars(
        select(models.QueueEntry)
        .where(models.QueueEntry.room_id == room_id)
        .order_by(models.QueueEntry.position)
    )
    return list(entries)


@router.post(
    "/{room_id}/queue",
    response_model=schemas.QueueEntryRead,
    status_code=201,
)
def enqueue_track(
    room_id: str,
    payload: schemas.QueueEntryCreate,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    track = session.get(models.Track, payload.track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    last_position = session.scalar(
        select(func.max(models.QueueEntry.position)).where(
            models.QueueEntry.room_id == room_id
        )
    )
    next_position = (last_position or 0) + 1

    entry = models.QueueEntry(
        room_id=room_id,
        track_id=payload.track_id,
        position=next_position,
        note=payload.note,
    )

    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.delete("/queue/{entry_id}", status_code=204)
def delete_queue_entry(entry_id: str, session: Session = Depends(get_session)):
    entry = session.get(models.QueueEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    session.delete(entry)
    session.commit()


@router.post("/{room_id}/queue/pop", response_model=schemas.QueueEntryRead)
def pop_next_queue(room_id: str, session: Session = Depends(get_session)):
    entry = session.scalar(
        select(models.QueueEntry)
        .where(models.QueueEntry.room_id == room_id)
        .order_by(models.QueueEntry.position)
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Queue is empty")
    session.delete(entry)
    session.commit()
    return entry
