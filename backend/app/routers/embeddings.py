from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_session


router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("", response_model=schemas.EmbeddingRead, status_code=201)
def upsert_embedding(
    payload: schemas.EmbeddingCreate,
    session: Session = Depends(get_session),
):
    embedding = session.scalar(
        select(models.Embedding).where(
            models.Embedding.entity_type == payload.entity_type,
            models.Embedding.entity_id == payload.entity_id,
        )
    )
    if embedding:
        embedding.vector = payload.vector
        embedding.model_version = payload.model_version
        embedding.dimensionality = len(payload.vector)
    else:
        embedding = models.Embedding(
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            vector=payload.vector,
            model_version=payload.model_version,
            dimensionality=len(payload.vector),
        )
    session.add(embedding)
    session.commit()
    session.refresh(embedding)
    return embedding


@router.get("/{entity_type}/{entity_id}", response_model=schemas.EmbeddingRead)
def fetch_embedding(entity_type: models.EntityKind, entity_id: str, session: Session = Depends(get_session)):
    embedding = session.scalar(
        select(models.Embedding).where(
            models.Embedding.entity_type == entity_type,
            models.Embedding.entity_id == entity_id,
        )
    )
    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")
    return embedding
