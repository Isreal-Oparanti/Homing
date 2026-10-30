from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, require_user

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    id: str
    email: str
    name: str | None


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(require_user)) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, name=user.name)
