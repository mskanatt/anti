import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Device, User
from .security import decode_jwt

_bearer = HTTPBearer(auto_error=False)


def _payload(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None:
        raise HTTPException(401, "Требуется авторизация", headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_jwt(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "Токен недействителен или истёк", headers={"WWW-Authenticate": "Bearer"})


def current_staff(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    payload = _payload(creds)
    if payload["role"] != "staff":
        raise HTTPException(403, "Доступно только администрации")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "Аккаунт не найден или отключён")
    return user


def current_device(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> Device:
    payload = _payload(creds)
    if payload["role"] != "device":
        raise HTTPException(403, "Доступно только устройствам")
    device = db.get(Device, payload["sub"])
    if device is None or not device.is_active:
        raise HTTPException(401, "Устройство не найдено или отключено")
    return device


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None