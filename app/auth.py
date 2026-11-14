import hmac
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import get_db
from app.mail import send_code
from app.models import LoginChallenge, LoginSession, User
from app.schemas import Login, Profile, Refresh, Register, UserRead, Verify
from app.security import (
    DUMMY_HASH,
    auth_limits,
    current_user,
    digest,
    passwords,
    token_pair,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", status_code=202)
def register(payload: Register, request: Request, db=Depends(get_db)):
    if not settings.registration_enabled:
        raise HTTPException(403, "Novos cadastros estão temporariamente indisponíveis.")
    auth_limits(request, str(payload.email))
    hashed = passwords.hash(payload.password)
    user = User(name=payload.name, email=str(payload.email).lower(), password_hash=hashed)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"message": "Se o cadastro puder ser realizado, acesse com e-mail e senha."}


@router.post("/login")
def login(payload: Login, request: Request, db=Depends(get_db)):
    dev = auth_limits(request, str(payload.email))
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    valid = passwords.verify(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "Credenciais inválidas")
    # Serialize new challenges per account; only the most recent challenge stays active.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    db.execute(
        update(LoginChallenge).where(LoginChallenge.user_id == user.id).values(consumed=True)
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = secrets.token_hex(32)
    challenge = LoginChallenge(
        id=challenge_id,
        user_id=user.id,
        device_hash=dev,
        code_hash=digest(challenge_id + code),
        expires_at=int(time.time()) + 300,
    )
    db.add(challenge)
    try:
        send_code(user.email, code)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(503, "Não foi possível enviar o código. Tente novamente mais tarde.")
    return {"challenge_id": challenge_id, "expires_in": 300}


@router.post("/verify")
def verify(payload: Verify, request: Request, db=Depends(get_db)):
    dev = auth_limits(request)
    challenge = db.scalar(
        select(LoginChallenge).where(LoginChallenge.id == payload.challenge_id).with_for_update()
    )
    error = HTTPException(401, "Código inválido ou expirado")
    if (
        not challenge
        or challenge.consumed
        or challenge.attempts >= 5
        or challenge.expires_at <= int(time.time())
        or challenge.device_hash != dev
    ):
        raise error
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, digest(challenge.id + payload.code)):
        db.commit()
        raise error
    challenge.consumed = True
    raw = secrets.token_urlsafe(48)
    session = LoginSession(
        id=secrets.token_hex(32),
        user_id=challenge.user_id,
        device_hash=dev,
        refresh_hash=digest(raw),
        expires_at=int(time.time()) + 30 * 86400,
    )
    db.add(session)
    db.commit()
    return token_pair(session, session.id + "." + raw)


@router.post("/refresh")
def refresh(payload: Refresh, request: Request, db=Depends(get_db)):
    dev = auth_limits(request)
    try:
        sid, raw = payload.refresh_token.split(".", 1)
    except ValueError:
        raise HTTPException(401, "Sessão inválida")
    session = db.scalar(select(LoginSession).where(LoginSession.id == sid).with_for_update())
    if (
        not session
        or session.revoked
        or session.expires_at <= int(time.time())
        or session.device_hash != dev
    ):
        raise HTTPException(401, "Sessão inválida")
    if not hmac.compare_digest(session.refresh_hash, digest(raw)):
        session.revoked = True
        db.commit()
        raise HTTPException(401, "Sessão inválida")
    raw = secrets.token_urlsafe(48)
    session.refresh_hash = digest(raw)
    db.commit()
    return token_pair(session, session.id + "." + raw)


@router.post("/logout", status_code=204)
def logout(request: Request, user=Depends(current_user), db=Depends(get_db)):
    db.execute(
        update(LoginSession)
        .where(LoginSession.id == request.state.session_id, LoginSession.user_id == user.id)
        .values(revoked=True)
    )
    db.commit()


@router.post("/logout-all", status_code=204)
def logout_all(user=Depends(current_user), db=Depends(get_db)):
    db.execute(update(LoginSession).where(LoginSession.user_id == user.id).values(revoked=True))
    db.commit()


@router.get("/me", response_model=UserRead)
def me(user=Depends(current_user)):
    return user


@router.patch("/me", response_model=UserRead)
def profile(payload: Profile, user=Depends(current_user), db=Depends(get_db)):
    user.name = payload.name.strip()
    if len(user.name) < 2:
        raise HTTPException(422, "Nome inválido")
    db.commit()
    return user
