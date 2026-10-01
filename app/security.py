import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException, Request
from sqlalchemy import select

from .db import AuthSession, SessionLocal, User, now


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + key.hex()


def verify_password(password, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password("not-a-real-user-password")


def current_user(request: Request):
    token = request.cookies.get("txtzi_session", "")
    if not token or len(token) > 128:
        raise HTTPException(401, "Sign in to continue.")
    with SessionLocal() as db:
        session = db.get(AuthSession, digest(token))
        if not session or session.expires_at < now():
            raise HTTPException(401, "Your session has expired. Please sign in again.")
        user = db.get(User, session.user_id)
        if not user:
            raise HTTPException(401, "Sign in to continue.")
        return user


def admin_user(request: Request):
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(403, "Administrator access required.")
    return user


_limits = OrderedDict()
_lock = threading.Lock()


def rate_limit(request: Request, bucket: str, maximum=20, seconds=60):
    # Trust no client-supplied forwarding header. Configure Uvicorn's trusted proxy IPs.
    ip = request.client.host if request.client else "unknown"
    key = (bucket, ip)
    clock = time.monotonic()
    with _lock:
        hits = [t for t in _limits.get(key, []) if t > clock - seconds]
        if len(hits) >= maximum:
            raise HTTPException(429, "Please wait a moment before trying again.", headers={"Retry-After": str(seconds)})
        hits.append(clock)
        _limits[key] = hits
        _limits.move_to_end(key)
        while len(_limits) > 10000:
            _limits.popitem(last=False)
