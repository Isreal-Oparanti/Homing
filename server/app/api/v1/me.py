from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_user
from app.db.repo.users import ensure_user
from app.db.session import get_db

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    id: str
    email: str
    name: str | None


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)) -> MeResponse:
    """Creates the user the first time we see them (docs/09-security-privacy.md)."""
    ensure_user(db, user)
    db.commit()
    return MeResponse(id=user.id, email=user.email, name=user.name)
