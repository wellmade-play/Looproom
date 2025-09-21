from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .. import models


def upsert_playback_state(
    session: Session,
    room: models.Room,
    track: models.Track,
    start_ts: Optional[datetime],
    offset_ms: int,
    is_paused: bool,
    listeners: Optional[int],
) -> models.PlaybackState:
    """Create or update the playback state for a room."""

    now = datetime.utcnow()
    start = start_ts or now
    state = room.playback_state
    previous_track_id = state.track_id if state else None
    track_changed = previous_track_id != track.id

    if state is None:
        state = models.PlaybackState(
            room_id=room.id,
            track_id=track.id,
            start_ts=start,
            anchor_server_ts=now,
            offset_ms=offset_ms,
            is_paused=is_paused,
            listeners=listeners or 0,
        )
        session.add(state)
    else:
        state.track_id = track.id
        state.start_ts = start
        state.offset_ms = offset_ms
        state.is_paused = is_paused
        state.anchor_server_ts = now
        if listeners is not None:
            state.listeners = listeners

    if track_changed and previous_track_id:
        _close_active_history(session, room.id, previous_track_id, now)

    if track_changed:
        _create_history(session, room.id, track.id, now)
        track.play_count += 1
        track.last_played_at = now
    else:
        track.last_played_at = track.last_played_at or now

    session.add(track)
    session.flush()

    return state


def _close_active_history(
    session: Session, room_id: str, track_id: str, ended_at: datetime
) -> None:
    history = session.scalar(
        select(models.RoomTrackHistory)
        .where(models.RoomTrackHistory.room_id == room_id)
        .where(models.RoomTrackHistory.track_id == track_id)
        .order_by(models.RoomTrackHistory.played_at.desc())
    )
    if history and history.ended_at is None:
        history.ended_at = ended_at
        session.add(history)


def _create_history(session: Session, room_id: str, track_id: str, played_at: datetime) -> None:
    entry = models.RoomTrackHistory(
        room_id=room_id,
        track_id=track_id,
        played_at=played_at,
    )
    session.add(entry)

def update_room_listener_count(session: Session, room: models.Room) -> int:
    """Recalculate the active listener count for a room's playback state."""

    active_count = session.scalar(
        select(func.count())
        .select_from(models.RoomMembership)
        .where(models.RoomMembership.room_id == room.id)
        .where(models.RoomMembership.left_at.is_(None))
    ) or 0

    if room.playback_state:
        room.playback_state.listeners = active_count
        session.add(room.playback_state)

    return active_count


def resume_room_playback(session: Session, room: models.Room, listeners: int | None = None) -> None:
    """Resume playback for a room if it is currently paused."""

    state = room.playback_state
    if state is None or state.track is None:
        return

    if listeners is not None and listeners != state.listeners:
        state.listeners = listeners

    if not state.is_paused:
        session.add(state)
        return

    offset = state.offset_ms or 0
    now = datetime.now(timezone.utc)
    start_ts = now - timedelta(milliseconds=offset) if offset > 0 else now

    upsert_playback_state(
        session=session,
        room=room,
        track=state.track,
        start_ts=start_ts,
        offset_ms=offset,
        is_paused=False,
        listeners=listeners if listeners is not None else state.listeners,
    )


def pause_room_playback(session: Session, room: models.Room, listeners: int | None = None) -> None:
    """Pause playback for a room, capturing the latest offset."""

    state = room.playback_state
    if state is None or state.track is None:
        return

    if state.is_paused:
        if listeners is not None and listeners != state.listeners:
            state.listeners = listeners
            session.add(state)
        return

    now = datetime.now(timezone.utc)
    anchor = state.anchor_server_ts or now
    elapsed_ms = max(int((now - anchor).total_seconds() * 1000), 0)
    offset = (state.offset_ms or 0) + elapsed_ms

    upsert_playback_state(
        session=session,
        room=room,
        track=state.track,
        start_ts=state.start_ts or now - timedelta(milliseconds=offset),
        offset_ms=offset,
        is_paused=True,
        listeners=listeners if listeners is not None else state.listeners,
    )
