import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal, get_db
from app.models import LoginSession, RateBucket, User

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False)


def digest(value: str):
    return hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def limit(scope: str, identity: str, maximum: int, seconds: int):
    """Shared atomic fixed windows in SQL, independent of worker/process memory."""
    now = int(time.time())
    window = now // seconds
    key = digest(f"{scope}:{identity}:{window}")
    with SessionLocal() as db:
        try:
            db.add(RateBucket(key=key, count=0, expires_at=(window + 1) * seconds))
            db.commit()
        except IntegrityError:
            db.rollback()
        result = db.execute(
            update(RateBucket)
            .where(RateBucket.key == key, RateBucket.count < maximum)
            .values(count=RateBucket.count + 1)
        )
        db.commit()
        if result.rowcount != 1:
            raise HTTPException(
                429,
                "Muitas tentativas. Aguarde e tente novamente.",
                headers={"Retry-After": str((window + 1) * seconds - now)},
            )


def device(request: Request):
    raw = request.headers.get("x-device-id", "")
    try:
        from uuid import UUID

        canonical = str(UUID(raw))
    except ValueError:
        raise HTTPException(400, "Identificador de instalação inválido")
    return digest(canonical)


def auth_limits(request: Request, account: str = ""):
    ip = request.client.host if request.client else "unknown"
    limit("auth-ip", ip, 30, 900)
    dev = device(request)
    limit("auth-device", dev, 20, 900)
    if account:
        limit("auth-account", account.lower(), 10, 900)
    return dev


def token_pair(session: LoginSession, refresh: str):
    now = int(time.time())
    access = jwt.encode(
        {
            "sub": str(session.user_id),
            "sid": session.id,
            "iat": now,
            "nbf": now,
            "exp": now + 600,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "jti": secrets.token_hex(16),
            "type": "access",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 600,
    }


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db=Depends(get_db),
):
    error = HTTPException(
        401, "Sessão inválida ou expirada", headers={"WWW-Authenticate": "Bearer"}
    )
    if not credentials:
        raise error
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "sid", "exp", "iat", "nbf", "iss", "aud", "jti", "type"]},
        )
        if claims["type"] != "access":
            raise error
        session = db.get(LoginSession, claims["sid"])
        if (
            not session
            or session.revoked
            or session.expires_at <= int(time.time())
            or str(session.user_id) != claims["sub"]
            or session.device_hash != device(request)
        ):
            raise error
        user = db.get(User, session.user_id)
        if not user:
            raise error
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise error
    limit("user", str(user.id), 180, 60)
    limit("session-device", session.device_hash, 180, 60)
    request.state.session_id = session.id
    return user
