"""Requests come only from the Next.js server, which adds a shared secret and the user's identity.

See docs/adr/0005-auth-proxy.md.
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import AppError

DEMO_USER_ID = "demo"  # the "Try the demo" login (web/lib/auth.ts)
TICKET_SECONDS = 300  # how long an upload ticket lasts (web/lib/server/backend.ts)


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


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _signed(body: str, secret: str) -> str:
    key = hmac.new(secret.encode(), b"upload-ticket", hashlib.sha256).digest()
    return f"{body}.{_b64(hmac.new(key, body.encode(), hashlib.sha256).digest())}"


def sign_ticket(payload: dict[str, object], secret: str) -> str:
    """The same signing as web/lib/server/backend.ts; tests use it to make tickets."""
    return _signed(_b64(json.dumps(payload, separators=(",", ":")).encode()), secret)


def user_from_ticket(ticket: str, secret: str, now: float | None = None) -> CurrentUser | None:
    """Who an upload ticket was signed for, or None if it's forged, malformed or expired."""
    body, _, _ = ticket.partition(".")
    if not secret or not body:
        return None
    if not hmac.compare_digest(_signed(body, secret).encode(), ticket.encode()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("exp"), int):
        return None
    if data["exp"] < (time.time() if now is None else now):
        return None
    uid, email, name = data.get("uid"), data.get("email"), data.get("name")
    if not isinstance(uid, str) or not uid or not isinstance(email, str) or not email:
        return None
    return CurrentUser(id=uid, email=email, name=name if isinstance(name, str) else None)


def require_uploader(
    authorization: str | None = Header(default=None),
    proxy_secret: str | None = Header(default=None, alias="X-Homing-Proxy-Secret"),
    user_id: str | None = Header(default=None, alias="X-Homing-User-Id"),
    user_email: str | None = Header(default=None, alias="X-Homing-User-Email"),
    user_name: str | None = Header(default=None, alias="X-Homing-User-Name"),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Uploads also accept a ticket, so files go from the browser straight to the API:
    Vercel caps request bodies at 4.5 MB, and files may be 10 MB."""
    if authorization and authorization.startswith("Bearer "):
        user = user_from_ticket(authorization.removeprefix("Bearer "), settings.proxy_secret)
        if user is None:
            raise AppError("unauthorized", "Please sign in again.", status=401)
        return user
    return require_user(proxy_secret, user_id, user_email, user_name, settings)
