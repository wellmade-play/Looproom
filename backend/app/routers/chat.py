from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session


router = APIRouter(prefix="/rooms", tags=["chat"])


@router.get("/{room_id}/messages", response_model=list[schemas.ChatMessageRead])
def list_messages(
    room_id: str,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    stmt = (
        select(models.ChatMessage)
        .where(models.ChatMessage.room_id == room_id)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(limit)
    )
    if since:
        stmt = stmt.where(models.ChatMessage.created_at >= since)

    messages = session.scalars(stmt)
    return list(reversed(list(messages)))


@router.post(
    "/{room_id}/messages",
    response_model=schemas.ChatMessageRead,
    status_code=201,
)
def post_message(
    room_id: str,
    payload: schemas.ChatMessageCreate,
    session: Session = Depends(get_session),
):
    room = session.get(models.Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    user = session.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    message = models.ChatMessage(room_id=room_id, **payload.model_dump())
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


@router.post(
    "/messages/{message_id}/reactions",
    response_model=schemas.ReactionRead,
    status_code=201,
)
def react_to_message(
    message_id: str,
    payload: schemas.ReactionCreate,
    session: Session = Depends(get_session),
):
    message = session.get(models.ChatMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    user = session.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reaction = models.Reaction(
        message_id=message_id,
        user_id=payload.user_id,
        type=payload.type,
    )

    session.add(reaction)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(status_code=409, detail="Reaction already exists")
    session.refresh(reaction)
    return reaction


@router.delete("/reactions/{reaction_id}", status_code=204)
def delete_reaction(reaction_id: str, session: Session = Depends(get_session)):
    reaction = session.get(models.Reaction, reaction_id)
    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")
    session.delete(reaction)
    session.commit()
