from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RoomMode(str, enum.Enum):
    LIVE = "live"
    OFFSET = "offset"
    FOCUS = "focus"


class VoiceRole(str, enum.Enum):
    HOST = "host"
    SPEAKER = "speaker"
    LISTENER = "listener"


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    MODERATOR = "moderator"
    MEMBER = "member"


class ReactionType(str, enum.Enum):
    LIKE = "like"
    LAUGH = "laugh"
    FIRE = "fire"
    QUESTION = "question"


class ModerationAction(str, enum.Enum):
    FLAG = "flag"
    HIDE = "hide"
    TIMEOUT = "timeout"
    DELETE = "delete"
    ESCALATE = "escalate"


class EntityKind(str, enum.Enum):
    ROOM = "room"
    MESSAGE = "message"
    USER = "user"
    TRACK = "track"
    ARTIST = "artist"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


def _uuid() -> str:
    return str(uuid4())


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    spotify_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    country: Mapped[Optional[str]] = mapped_column(String(8))
    product: Mapped[Optional[str]] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), default="ja")
    preferences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    access_token: Mapped[str] = mapped_column(String(512), nullable=False)
    refresh_token: Mapped[str] = mapped_column(String(512), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(String(512))
    reputation: Mapped[float] = mapped_column(Float, default=0.0)

    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="author", cascade="all, delete-orphan"
    )
    reactions: Mapped[List["Reaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memberships: Mapped[List["RoomMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Artist(TimestampMixin, Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    spotify_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    spotify_uri: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    spotify_url: Mapped[Optional[str]] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    official_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    rooms: Mapped[List["Room"]] = relationship(back_populates="artist")
    tracks: Mapped[List["Track"]] = relationship(back_populates="artist")



class Room(TimestampMixin, Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artist_id: Mapped[str] = mapped_column(ForeignKey("artists.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    mode: Mapped[RoomMode] = mapped_column(Enum(RoomMode), default=RoomMode.LIVE)
    rules: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    pinned_message_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    live_track_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    focus_level: Mapped[Optional[int]] = mapped_column(Integer)

    artist: Mapped["Artist"] = relationship(back_populates="rooms")
    live_track: Mapped[Optional["Track"]] = relationship(
        "Track", foreign_keys=[live_track_id], post_update=True
    )
    playback_state: Mapped[Optional["PlaybackState"]] = relationship(
        back_populates="room",
        uselist=False,
        cascade="all, delete-orphan",
    )
    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    queue_entries: Mapped[List["QueueEntry"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="QueueEntry.position",
    )
    memberships: Mapped[List["RoomMembership"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    histories: Mapped[List["RoomTrackHistory"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    voice_sessions: Mapped[List["VoiceSession"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    recommendation_events: Mapped[List["RecommendationEvent"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class Track(TimestampMixin, Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artist_id: Mapped[str] = mapped_column(ForeignKey("artists.id"), nullable=False)
    spotify_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    spotify_uri: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    uri: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    album_name: Mapped[Optional[str]] = mapped_column(String(200))
    album_uri: Mapped[Optional[str]] = mapped_column(String(64))
    album_image_url: Mapped[Optional[str]] = mapped_column(String(512))
    disc_number: Mapped[int] = mapped_column(Integer, default=1)
    track_number: Mapped[int] = mapped_column(Integer, default=0)
    explicit: Mapped[bool] = mapped_column(Boolean, default=False)
    preview_url: Mapped[Optional[str]] = mapped_column(String(512))
    isrc: Mapped[Optional[str]] = mapped_column(String(32))
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    audio_features: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    lyrics_ref: Mapped[Optional[str]] = mapped_column(String(255))
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    artist: Mapped["Artist"] = relationship(back_populates="tracks")
    histories: Mapped[List["RoomTrackHistory"]] = relationship(back_populates="track")
    queue_entries: Mapped[List["QueueEntry"]] = relationship(back_populates="track")
    playback_states: Mapped[List["PlaybackState"]] = relationship(back_populates="track")



class PlaybackState(TimestampMixin, Base):
    __tablename__ = "playback_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), unique=True)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anchor_server_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    offset_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    listeners: Mapped[int] = mapped_column(Integer, default=0)

    room: Mapped["Room"] = relationship(back_populates="playback_state")
    track: Mapped["Track"] = relationship(back_populates="playback_states")


class RoomTrackHistory(Base):
    __tablename__ = "room_track_history"
    __table_args__ = (
        UniqueConstraint("room_id", "played_at", name="uq_room_track_play"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    was_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    score_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

    room: Mapped["Room"] = relationship(back_populates="histories")
    track: Mapped["Track"] = relationship(back_populates="histories")


class RoomMembership(TimestampMixin, Base):
    __tablename__ = "room_memberships"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole), default=MembershipRole.MEMBER
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    room: Mapped["Room"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class QueueEntry(TimestampMixin, Base):
    __tablename__ = "queue_entries"
    __table_args__ = (
        UniqueConstraint("room_id", "position", name="uq_room_queue_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    requested_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(160))

    room: Mapped["Room"] = relationship(back_populates="queue_entries")
    track: Mapped["Track"] = relationship(back_populates="queue_entries")
    requested_by: Mapped[Optional["User"]] = relationship()


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    track_position_ms: Mapped[Optional[int]] = mapped_column(Integer)
    lang: Mapped[str] = mapped_column(String(8), default="ja")
    toxic_score: Mapped[Optional[float]] = mapped_column(Float)
    sentiment: Mapped[Optional[float]] = mapped_column(Float)

    room: Mapped["Room"] = relationship(back_populates="messages")
    author: Mapped["User"] = relationship(back_populates="messages")
    reactions: Mapped[List["Reaction"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class Reaction(TimestampMixin, Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "type", name="uq_reaction_unique"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(ForeignKey("chat_messages.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[ReactionType] = mapped_column(Enum(ReactionType), nullable=False)

    message: Mapped["ChatMessage"] = relationship(back_populates="reactions")
    user: Mapped["User"] = relationship(back_populates="reactions")


class VoiceSession(TimestampMixin, Base):
    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    sfu_room_id: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[VoiceRole] = mapped_column(Enum(VoiceRole), default=VoiceRole.HOST)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    participant_count: Mapped[int] = mapped_column(Integer, default=0)

    room: Mapped["Room"] = relationship(back_populates="voice_sessions")


class RecommendationEvent(TimestampMixin, Base):
    __tablename__ = "recommendation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    input_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    ranked_list: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    chosen_track_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tracks.id"))

    room: Mapped["Room"] = relationship(back_populates="recommendation_events")
    chosen_track: Mapped[Optional["Track"]] = relationship()


class ModerationLog(TimestampMixin, Base):
    __tablename__ = "moderation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[EntityKind] = mapped_column(Enum(EntityKind), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[ModerationAction] = mapped_column(
        Enum(ModerationAction), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_json: Mapped[Dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    issued_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))


class SpotifyAuthState(TimestampMixin, Base):
    __tablename__ = "spotify_auth_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    redirect_uri: Mapped[Optional[str]] = mapped_column(String(512))


class Embedding(TimestampMixin, Base):

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_embedding_entity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[EntityKind] = mapped_column(Enum(EntityKind), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    vector: Mapped[List[float]] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(40), default="v0")
    dimensionality: Mapped[int] = mapped_column(Integer, default=0)


__all__ = [
    "User",
    "Artist",
    "Room",
    "Track",
    "PlaybackState",
    "RoomTrackHistory",
    "RoomMembership",
    "QueueEntry",
    "ChatMessage",
    "Reaction",
    "VoiceSession",
    "RecommendationEvent",
    "ModerationLog",
    "Embedding",
    "SpotifyAuthState",
    "RoomMode",
    "ReactionType",
    "MembershipRole",
    "VoiceRole",
    "ModerationAction",
    "EntityKind",
]

