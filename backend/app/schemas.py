from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import (
    EntityKind,
    MembershipRole,
    ModerationAction,
    ReactionType,
    RoomMode,
    VoiceRole,
)


class ORMModel(BaseModel):
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "protected_namespaces": (),
    }


class Timestamped(ORMModel):
    created_at: datetime
    updated_at: datetime


class SpotifyPlaybackToken(BaseModel):
    access_token: str = Field(..., min_length=1)
    expires_in: int = Field(..., ge=0)


class UserRead(Timestamped):
    id: str
    spotify_id: str
    display_name: str
    avatar_url: Optional[str]
    email: Optional[str]
    country: Optional[str]
    product: Optional[str]
    preferences: Dict[str, Any]


class ArtistBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    official_flag: bool = False


class ArtistCreate(ArtistBase):
    pass


class ArtistRead(Timestamped):
    id: str
    spotify_id: str
    spotify_uri: str
    name: str
    followers: int
    popularity: int
    spotify_url: Optional[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    official_flag: bool


class TrackBase(BaseModel):
    artist_id: str
    title: str = Field(..., min_length=1, max_length=200)
    uri: str = Field(..., max_length=255)
    duration_ms: int = Field(..., ge=0)
    audio_features: Dict[str, Any] = Field(default_factory=dict)
    lyrics_ref: Optional[str] = Field(default=None, max_length=255)


class TrackCreate(TrackBase):
    pass


class TrackRead(Timestamped):
    id: str
    artist_id: str
    spotify_id: str
    spotify_uri: str
    title: str
    uri: str
    duration_ms: int
    album_name: Optional[str]
    album_uri: Optional[str]
    album_image_url: Optional[str]
    disc_number: int
    track_number: int
    explicit: bool
    preview_url: Optional[str]
    isrc: Optional[str]
    popularity: int
    audio_features: Dict[str, Any]
    lyrics_ref: Optional[str]
    play_count: int
    skip_count: int
    last_played_at: Optional[datetime]


class RoomBase(BaseModel):
    artist_id: str
    name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = None
    mode: RoomMode = RoomMode.LIVE
    rules: Dict[str, Any] = Field(default_factory=dict)
    focus_level: Optional[int] = Field(default=None, ge=0)
    is_featured: bool = False


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = None
    mode: Optional[RoomMode] = None
    rules: Optional[Dict[str, Any]] = None
    focus_level: Optional[int] = Field(default=None, ge=0)
    is_featured: Optional[bool] = None
    live_track_id: Optional[str] = None


class RoomRead(Timestamped):
    id: str
    artist_id: str
    name: str
    description: Optional[str]
    mode: RoomMode
    rules: Dict[str, Any]
    pinned_message_ids: List[str]
    live_track_id: Optional[str]
    is_featured: bool
    focus_level: Optional[int]
    playback_state: Optional[PlaybackStateRead] = None


class QueueEntryCreate(BaseModel):
    track_id: str
    note: Optional[str] = Field(default=None, max_length=160)


class QueueEntryRead(Timestamped):
    id: str
    room_id: str
    track_id: str
    position: int
    note: Optional[str]
    requested_by_id: Optional[str]


class MembershipRead(Timestamped):
    id: str
    room_id: str
    user_id: str
    role: MembershipRole
    joined_at: datetime
    left_at: Optional[datetime]


class PlaybackStateUpdate(BaseModel):
    track_id: str
    start_ts: Optional[datetime] = None
    offset_ms: int = Field(0, ge=0)
    is_paused: bool = False
    listeners: Optional[int] = Field(default=None, ge=0)


class PlaybackStateRead(Timestamped):
    id: str
    room_id: str
    track_id: str
    start_ts: datetime
    anchor_server_ts: datetime
    offset_ms: int
    is_paused: bool
    listeners: int
    track: Optional[TrackRead] = None


class ChatMessageCreate(BaseModel):
    user_id: str
    body: str = Field(..., min_length=1, max_length=2000)
    track_position_ms: Optional[int] = Field(default=None, ge=0)
    lang: str = Field("ja", max_length=8)
    toxic_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sentiment: Optional[float] = Field(default=None, ge=-1.0, le=1.0)


class ChatMessageRead(Timestamped):
    id: str
    room_id: str
    user_id: str
    body: str
    track_position_ms: Optional[int]
    lang: str
    toxic_score: Optional[float]
    sentiment: Optional[float]


class ReactionCreate(BaseModel):
    user_id: str
    type: ReactionType


class ReactionRead(Timestamped):
    id: str
    message_id: str
    user_id: str
    type: ReactionType


class VoiceSessionCreate(BaseModel):
    sfu_room_id: str
    role: VoiceRole = VoiceRole.HOST
    participant_count: Optional[int] = Field(default=0, ge=0)


class VoiceSessionRead(Timestamped):
    id: str
    room_id: str
    sfu_room_id: str
    role: VoiceRole
    is_active: bool
    started_at: datetime
    ended_at: Optional[datetime]
    participant_count: int


class RecommendationRequest(BaseModel):
    limit: int = Field(10, ge=1, le=50)
    include_recent: bool = True


class RecommendationItem(BaseModel):
    track_id: str
    score: float
    breakdown: Dict[str, float]


class RecommendationResponse(BaseModel):
    room_id: str
    generated_at: datetime
    event_id: str
    items: List[RecommendationItem]


class RecommendationAccept(BaseModel):
    track_id: str
    source: str = Field("manual")


class ModerationLogCreate(BaseModel):
    entity_type: EntityKind
    entity_id: str
    action: ModerationAction
    reason: Optional[str] = Field(default=None, max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    issued_by: Optional[str] = None


class ModerationLogRead(Timestamped):
    id: str
    entity_type: EntityKind
    entity_id: str
    action: ModerationAction
    reason: Optional[str]
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    issued_by: Optional[str]


class EmbeddingCreate(BaseModel):
    entity_type: EntityKind
    entity_id: str
    vector: List[float]
    model_version: str = "v0"


class EmbeddingRead(Timestamped):
    id: str
    entity_type: EntityKind
    entity_id: str
    vector: List[float]
    model_version: str
    dimensionality: int


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime

class RoomJoinRequest(BaseModel):
    user_id: str
    role: MembershipRole = MembershipRole.MEMBER


class RoomLeaveRequest(BaseModel):
    user_id: str


class SpotifyLoginResponse(BaseModel):
    auth_url: str
