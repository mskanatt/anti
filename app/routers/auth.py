import hmac

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Device, User
from ..ratelimit import rate_limit
from ..schemas import DeviceLogin, LoginRequest, StaffRegister, TokenResponse
from ..security import create_jwt, hash_password, hash_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_DUMMY_HASH = hash_password("dummy-password-for-timing-only")


@router.post(
    "/register-staff",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("register-staff", 10, 60))],
)
def register_staff(body: StaffRegister, db: Session = Depends(get_db)):
    if not hmac.compare_digest(body.invite_code.encode(), settings.staff_invite_code.encode()):
        raise HTTPException(403, "Неверный код приглашения")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Аккаунт с таким email уже существует")
    user = User(email=email, password_hash=hash_password(body.password), role="staff")
    db.add(user)
    db.commit()
    return TokenResponse(
        access_token=create_jwt(str(user.id), "staff", settings.staff_token_minutes), role="staff"
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", 10, 60))],
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not (user and password_ok and user.is_active):
        raise HTTPException(401, "Неверный email или пароль")
    return TokenResponse(
        access_token=create_jwt(str(user.id), "staff", settings.staff_token_minutes), role="staff"
    )


@router.post(
    "/device-login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("device-login", 30, 60))],
)
def device_login(body: DeviceLogin, db: Session = Depends(get_db)):
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(body.device_token)))
    if device is None or not device.is_active:
        raise HTTPException(401, "Устройство не найдено или отключено")
    return TokenResponse(
        access_token=create_jwt(device.id, "device", settings.device_token_minutes), role="device"
    )