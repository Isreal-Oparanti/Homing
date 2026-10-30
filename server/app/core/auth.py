"""Requests come only from the Next.js server, which adds a shared secret and the user's identity.

See docs/adr/0005-auth-proxy.md.
"""

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str | None = None


def require_user(
    proxy_secret: str | None = Header(default=None, alias="X-Homing-Proxy-Secret"),
    user_id: str | None = Header(default=None, alias="X-Homing-User-Id"),
    user_email: str | None = Header(default=None, alias="X-Homing-User-Email"),
    user_name: str | None = Header(default=None, alias="X-Homing-User-Name"),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    expected = settings.proxy_secret
    if not expected or not proxy_secret or not hmac.compare_digest(proxy_secret, expected):
        raise AppError("unauthorized", "Please sign in again.", status=401)
    if not user_id or not user_email:
        raise AppError("unauthorized", "Please sign in again.", status=401)
    return CurrentUser(id=user_id, email=user_email, name=user_name)
