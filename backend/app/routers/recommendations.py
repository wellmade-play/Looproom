from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..services.recommendation import generate_room_recommendations


router = APIRouter(prefix="/rooms", tags=["recommendations"])


@router.get(
    "/{room_id}/recommendations",
    response_model=schemas.RecommendationResponse,
)
def fetch_recommendations(
    room_id: str,
    limit: int = Query(default=10, ge=1, le=25),
    include_recent: bool = Query(default=True),
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    items, context = generate_room_recommendations(
        session=session,
        room=room,
        limit=limit,
        include_recent=include_recent,
    )

    event = models.RecommendationEvent(
        room_id=room.id,
        input_context={
            "cvs": context.cvs,
            "window_minutes": context.window_minutes,
            "message_count": context.message_count,
            "user_count": context.user_count,
            "reaction_count": context.reaction_count,
        },
        ranked_list=[
            {"track_id": item.track_id, "score": item.score, "breakdown": item.breakdown}
            for item in items
        ],
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    response_items = [
        schemas.RecommendationItem(
            track_id=item.track_id,
            score=item.score,
            breakdown=item.breakdown,
        )
        for item in items
    ]

    return schemas.RecommendationResponse(
        room_id=room.id,
        generated_at=context.generated_at,
        event_id=event.id,
        items=response_items,
    )


@router.post(
    "/{room_id}/recommendations/accept",
    status_code=204,
)
def accept_recommendation(
    room_id: str,
    payload: schemas.RecommendationAccept,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    event = None
    if payload.event_id:
        event = session.get(models.RecommendationEvent, payload.event_id)
    if event is None:
        event = session.scalar(
            select(models.RecommendationEvent)
            .where(models.RecommendationEvent.room_id == room_id)
            .order_by(models.RecommendationEvent.created_at.desc())
        )
    if event is None:
        raise HTTPException(status_code=404, detail="Recommendation event not found")

    chosen_track = session.get(models.Track, payload.track_id)
    if not chosen_track:
        raise HTTPException(status_code=404, detail="Track not found")

    event.chosen_track_id = payload.track_id
    context = dict(event.input_context or {})
    context["accepted_source"] = payload.source
    context["accepted_at"] = context.get("accepted_at") or datetime.utcnow().isoformat()
    event.input_context = context

    session.add(event)
    session.commit()
