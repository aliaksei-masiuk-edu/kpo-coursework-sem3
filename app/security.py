import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from pwdlib import PasswordHash

from app.database import get_db
from app.models import LoginSession, User

password_hasher = PasswordHash.recommended()
COOKIE_NAME = "service_session"
# Для неизвестного логина пароль проверяется по фиктивному хешу, чтобы время ответа не отличалось.
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(24))


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, user):
    raw = secrets.token_urlsafe(32)
    session = LoginSession(
        token_hash=hash_token(raw),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(hours=8),
    )
    db.add(session)
    db.commit()
    return raw, session


def current_user(
    request: Request,
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    db=Depends(get_db),
):
    token = request.cookies.get(COOKIE_NAME)
    session = db.get(LoginSession, hash_token(token)) if token else None
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "Войдите в систему")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Учётная запись недоступна")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(csrf_token or "", session.csrf_token):
            raise HTTPException(403, "Обновите страницу и повторите действие")
    request.state.login_session = session
    return user


def admin_user(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Действие доступно только администратору")
    return user
