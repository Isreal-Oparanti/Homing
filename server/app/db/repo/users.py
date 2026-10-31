from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.models import User


def ensure_user(db: Session, user: CurrentUser) -> None:
    """Create the user the first time we see them. Later calls do nothing."""
    db.execute(
        insert(User).values(id=user.id, email=user.email, name=user.name).on_conflict_do_nothing()
    )
