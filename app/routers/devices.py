import re
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import TRIGGERS, settings
from ..database import get_db
from ..deps import current_device, current_staff
from ..models import Device, PairingCode, User, utcnow
from ..ratelimit import rate_limit
from ..schemas import (
    DeviceConfig,
    DeviceOut,
    DevicePatch,
    DeviceRegister,
    DeviceRegisterResponse,
    HeartbeatIn,
    PairingCodeOut,
    TriggerOut,
)
from ..security import create_jwt, hash_token, new_device_token

router = APIRouter(prefix="/devices", tags=["devices"])

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _normalize_code(raw: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
    return f"{cleaned[:4]}-{cleaned[4:]}"


def _device_out(d: Device) -> DeviceOut:
    fresh = d.last_seen is not None and (utcnow() - d.last_seen) < timedelta(
        seconds=settings.device_online_seconds
    )
    return DeviceOut(
        id=d.id,
        location=d.location,
        is_active=d.is_active,
        is_listening=d.is_listening,
        online=bool(d.is_active and d.is_listening and fresh),
        last_seen=d.last_seen,
    )


@router.post("/pairing-codes", response_model=PairingCodeOut, status_code=201)
def create_pairing_code(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    code = PairingCode(
        code=f"{raw[:4]}-{raw[4:]}",
        created_by=user.id,
        expires_at=utcnow() + timedelta(hours=settings.pairing_code_hours),
    )
    db.add(code)
    db.commit()
    return PairingCodeOut(code=code.code, expires_at=code.expires_at)


@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("device-register", 10, 60))],
)
def register_device(body: DeviceRegister, db: Session = Depends(get_db)):
    code = _normalize_code(body.pairing_code)
    now = utcnow()
    result = db.execute(
        update(PairingCode)
        .where(PairingCode.code == code, PairingCode.used_at.is_(None), PairingCode.expires_at > now)
        .values(used_at=now)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(403, "Код привязки недействителен или истёк")

    token = new_device_token()
    device = Device(id=str(uuid.uuid4()), location=body.location.strip(), token_hash=hash_token(token))
    db.add(device)
    db.commit()
    return DeviceRegisterResponse(
        device_id=device.id,
        device_token=token,
        access_token=create_jwt(device.id, "device", settings.device_token_minutes),
        location=device.location,
    )


@router.get("/config", response_model=DeviceConfig)
def device_config(device: Device = Depends(current_device)):
    return DeviceConfig(
        triggers=[TriggerOut(phrase=p, category=c) for p, c in TRIGGERS.items()],
        min_confidence=settings.min_confidence,
        cooldown_seconds=settings.alert_cooldown_seconds,
    )


@router.post("/heartbeat", status_code=204)
def heartbeat(body: HeartbeatIn, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    device.last_seen = utcnow()
    device.is_listening = body.listening
    db.add(device)
    db.commit()


@router.get("", response_model=list[DeviceOut])
def list_devices(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    devices = db.scalars(select(Device).order_by(Device.location)).all()
    return [_device_out(d) for d in devices]


@router.patch("/{device_id}", response_model=DeviceOut)
def patch_device(
    device_id: str,
    body: DevicePatch,
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Устройство не найдено")
    if body.is_active is not None:
        device.is_active = body.is_active
        if not body.is_active:
            device.is_listening = False
    if body.location is not None:
        device.location = body.location.strip()
    db.commit()
    return _device_out(device)