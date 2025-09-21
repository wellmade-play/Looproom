from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session
from ..security import get_current_user


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=schemas.UserRead)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("", response_model=list[schemas.UserRead])
def list_users(
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
):
    users = session.scalars(select(models.User).order_by(models.User.created_at.desc()))
    return list(users)


@router.get("/{user_id}", response_model=schemas.UserRead)
def get_user(
    user_id: str,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
):
    user = session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
