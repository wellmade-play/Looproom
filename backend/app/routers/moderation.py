from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session


router = APIRouter(prefix="/moderation", tags=["moderation"])


@router.post("/logs", response_model=schemas.ModerationLogRead, status_code=201)
def create_log(
    payload: schemas.ModerationLogCreate,
    session: Session = Depends(get_session),
):
    data = payload.model_dump()
    metadata = data.pop("metadata", {})
    log = models.ModerationLog(metadata_json=metadata, **data)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


@router.get("/logs", response_model=list[schemas.ModerationLogRead])
def list_logs(session: Session = Depends(get_session)):
    logs = session.scalars(select(models.ModerationLog).order_by(models.ModerationLog.created_at.desc()))
    return list(logs)

