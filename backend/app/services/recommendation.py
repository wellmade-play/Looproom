from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models


@dataclass
class RecommendationItem:
    track_id: str
    score: float
    breakdown: Dict[str, float]


@dataclass
class RecommendationContext:
    cvs: float
    window_minutes: int
    message_count: int
    user_count: int
    reaction_count: int
    generated_at: datetime


WINDOW_MINUTES = 20
ALPHA = 0.6
BETA = 0.25
GAMMA = 0.15
LAMBDA = 0.12

W1 = 0.35
W2 = 0.35
W3 = 0.2
W4 = 0.1


def generate_room_recommendations(
    session: Session, room: models.Room, limit: int = 10, include_recent: bool = True
) -> tuple[List[RecommendationItem], RecommendationContext]:
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=WINDOW_MINUTES)

    messages = session.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.room_id == room.id)
        .where(models.ChatMessage.created_at >= window_start)
    )
    messages = list(messages)
    message_count = len(messages)
    user_count = len({m.user_id for m in messages}) or 1

    reaction_count = session.scalar(
        select(func.count(models.Reaction.id))
        .join(models.ChatMessage, models.ChatMessage.id == models.Reaction.message_id)
        .where(models.ChatMessage.room_id == room.id)
        .where(models.ChatMessage.created_at >= window_start)
    ) or 0

    likes_count = session.scalar(
        select(func.count(models.Reaction.id))
        .join(models.ChatMessage, models.ChatMessage.id == models.Reaction.message_id)
        .where(models.ChatMessage.room_id == room.id)
        .where(models.ChatMessage.created_at >= window_start)
        .where(models.Reaction.type == models.ReactionType.LIKE)
    ) or 0

    last_message_ts: Optional[datetime] = max(
        (m.created_at for m in messages), default=room.updated_at
    )
    delta_minutes = (
        max((now - last_message_ts).total_seconds(), 0.0) / 60.0 if last_message_ts else 60.0
    )

    cvs = _compute_cvs(
        message_count=message_count,
        likes=likes_count,
        reactions=reaction_count,
        participant_count=user_count,
        delta_minutes=delta_minutes,
    )

    current_embedding = _get_track_embedding(session, room.live_track_id)

    history = session.scalars(
        select(models.RoomTrackHistory)
        .where(models.RoomTrackHistory.room_id == room.id)
        .order_by(models.RoomTrackHistory.played_at.desc())
        .limit(25)
    )
    recent_track_ids = [h.track_id for h in history]
    recent_seen = set(recent_track_ids[:5])

    candidates = session.scalars(
        select(models.Track).where(models.Track.artist_id == room.artist_id)
    )

    queue_track_ids = {
        entry.track_id
        for entry in session.scalars(
            select(models.QueueEntry).where(models.QueueEntry.room_id == room.id)
        )
    }

    items: List[RecommendationItem] = []
    for track in candidates:
        if not include_recent and track.id in recent_seen:
            continue
        if track.id == room.live_track_id:
            continue

        embedding = _get_track_embedding(session, track.id)
        cosine = _cosine_similarity(current_embedding, embedding) if embedding else 0.0
        novelty = _novelty_score(track)
        fatigue = _fatigue_penalty(track, recent_track_ids)
        queue_penalty = 0.1 if track.id in queue_track_ids else 0.0

        score = (
            W1 * cvs
            + W2 * cosine
            + W3 * novelty
            - W4 * (fatigue + queue_penalty)
        )
        breakdown = {
            "cvs": round(W1 * cvs, 4),
            "similarity": round(W2 * cosine, 4),
            "novelty": round(W3 * novelty, 4),
            "fatigue": round(W4 * fatigue, 4),
            "queue_penalty": round(W4 * queue_penalty, 4),
        }
        items.append(RecommendationItem(track_id=track.id, score=score, breakdown=breakdown))

    items.sort(key=lambda item: item.score, reverse=True)
    items = items[:limit]

    context = RecommendationContext(
        cvs=cvs,
        window_minutes=WINDOW_MINUTES,
        message_count=message_count,
        user_count=user_count,
        reaction_count=reaction_count,
        generated_at=now,
    )

    return items, context


def _compute_cvs(
    *,
    message_count: int,
    likes: int,
    reactions: int,
    participant_count: int,
    delta_minutes: float,
) -> float:
    numerator = ALPHA * message_count + BETA * likes + GAMMA * reactions
    base = numerator / math.sqrt(participant_count)
    decay = math.exp(-LAMBDA * delta_minutes)
    return round(base * decay, 4)


def _get_track_embedding(session: Session, track_id: Optional[str]) -> Optional[List[float]]:
    if not track_id:
        return None
    embedding = session.scalar(
        select(models.Embedding).where(
            models.Embedding.entity_type == models.EntityKind.TRACK,
            models.Embedding.entity_id == track_id,
        )
    )
    return embedding.vector if embedding else None


def _cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _novelty_score(track: models.Track) -> float:
    base = 1.0 / (1.0 + track.play_count)
    if track.last_played_at:
        minutes_since = (datetime.utcnow() - track.last_played_at).total_seconds() / 60
        boost = min(minutes_since / 120, 1.0)
        return round(base + 0.2 * boost, 4)
    return round(base + 0.2, 4)


def _fatigue_penalty(track: models.Track, recent_track_ids: List[str]) -> float:
    if track.id not in recent_track_ids:
        return 0.0
    index = recent_track_ids.index(track.id)
    return round(max(0.0, 1.0 - index / 5), 4)
