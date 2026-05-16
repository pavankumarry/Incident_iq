from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Session as UserSession

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SessionResponse(BaseModel):
    id: int
    user_id: int
    token: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes — CLEAN version: uses FastAPI DI so connection is always released
# ---------------------------------------------------------------------------
@router.get("/{user_id}", response_model=Optional[SessionResponse])
def get_session(user_id: int, db: DBSession = Depends(get_db)):
    """
    Return the most recent active session for a user.
    Uses FastAPI dependency injection — the DB connection is always released
    after the request, even if an exception is raised.
    """
    session = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.expires_at > datetime.utcnow(),
        )
        .order_by(UserSession.created_at.desc())
        .first()
    )
    return session


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(user_id: int, token: str, expires_at: datetime, db: DBSession = Depends(get_db)):
    """Manually create a session (used internally / for testing)."""
    session = UserSession(user_id=user_id, token=token, expires_at=expires_at)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
