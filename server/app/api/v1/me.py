from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents import is_it_true
from app.core.auth import CurrentUser, require_user
from app.core.errors import AppError
from app.db.models import Profile
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


class ProfileOut(BaseModel):
    """What Homing remembers about you, from your answers on save cards."""

    birth_year: int | None = None
    nationality: list[str] = []
    residence_country: str | None = None
    student_status: str | None = None
    education_level: str | None = None
    languages: dict[str, str] = {}
    company_registered: bool | None = None


@router.get("/me/profile", response_model=ProfileOut)
def get_profile(
    user: CurrentUser = Depends(require_user), db: Session = Depends(get_db)
) -> ProfileOut:
    profile = db.get(Profile, user.id)
    return ProfileOut.model_validate(profile, from_attributes=True) if profile else ProfileOut()


class ProfileAnswer(BaseModel):
    question_id: str
    value: str | int | bool | None


@router.put("/me/profile", response_model=ProfileOut)
def put_profile(
    body: ProfileAnswer,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """Change or forget one thing Homing remembers. Every opportunity is re-judged by code."""
    ensure_user(db, user)
    try:
        is_it_true.update_profile(db, user.id, body.question_id, body.value)
    except (is_it_true.BadAnswer, ValueError) as exc:
        raise AppError("bad_answer", str(exc) or "That answer doesn't fit.", status=422) from exc
    db.commit()
    return get_profile(user, db)
