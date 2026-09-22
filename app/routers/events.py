import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import TRIGGERS, settings
from ..database import get_db
from ..deps import client_ip, current_device, current_staff
from ..models import AccessLog, Device, Event, PushSubscription, User, utcnow
from .notifications import dispatch_alert
from ..schemas import AuditOut, EventCreated, EventIn, EventOut, EventPatch, EventStatus
from ..ws import hub

router = APIRouter(tags=["events"])

MAX_CLOCK_SKEW = timedelta(minutes=10)


def _event_out(e: Event) -> EventOut:
    return EventOut(
        id=e.id,
        device_id=e.device_id,
        device_location=e.device.location,
        occurred_at=e.occurred_at,
        trigger_word=e.trigger_word,
        category=e.category,
        confidence=e.confidence,
        status=e.status,
        handled_by_email=e.handler.email if e.handler else None,
        handled_at=e.handled_at,
    )


def _audit(db: Session, user: User, action: str, request: Request, details: dict | None = None) -> None:
    db.add(
        AccessLog(
            user_id=user.id,
            action=action,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            ip=client_ip(request),
        )
    )


@router.post("/events", response_model=EventCreated, status_code=201)
def create_event(
    body: EventIn,
    response: Response,
    background: BackgroundTasks,
    device: Device = Depends(current_device),
    db: Session = Depends(get_db),
):
    if body.device_id is not None and body.device_id != device.id:
        raise HTTPException(403, "device_id не совпадает с токеном")

    word = body.trigger_word.strip().lower()
    category = TRIGGERS.get(word)
    if category is None:
        raise HTTPException(422, "Неизвестный триггер")

    now = utcnow()
    occurred = now
    if body.timestamp is not None:
        ts = body.timestamp if body.timestamp.tzinfo else body.timestamp.replace(tzinfo=timezone.utc)
        if abs(ts - now) <= MAX_CLOCK_SKEW:
            occurred = ts.astimezone(timezone.utc)

    since = now - timedelta(seconds=settings.alert_cooldown_seconds)
    duplicate = db.scalar(
        select(Event.id)
        .where(Event.device_id == device.id, Event.trigger_word == word, Event.received_at >= since)
        .limit(1)
    )
    if duplicate is not None:
        response.status_code = 200
        return EventCreated(id=duplicate, deduplicated=True)

    event = Event(
        device_id=device.id,
        occurred_at=occurred,
        received_at=now,
        trigger_word=word,
        category=category,
        confidence=body.confidence,
    )
    event.device = device
    device.last_seen = now
    db.add(event)
    db.commit()

    payload = _event_out(event).model_dump(mode="json")
    subs = []
    if settings.push_enabled:
        subs = [
            {"id": s.id, "endpoint": s.endpoint, "p256dh": s.p256dh, "auth": s.auth}
            for s in db.scalars(select(PushSubscription))
        ]
    background.add_task(dispatch_alert, payload, subs)
    return EventCreated(id=event.id)


@router.get("/events", response_model=list[EventOut])
def list_events(
    request: Request,
    device_id: str | None = None,
    status: EventStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    query = (
        select(Event)
        .options(joinedload(Event.device), joinedload(Event.handler))
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if device_id:
        query = query.where(Event.device_id == device_id)
    if status:
        query = query.where(Event.status == status)
    if date_from:
        query = query.where(Event.occurred_at >= date_from)
    if date_to:
        query = query.where(Event.occurred_at <= date_to)

    rows = db.scalars(query).unique().all()
    _audit(
        db,
        user,
        "view_events",
        request,
        {
            "device_id": device_id,
            "status": status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "offset": offset,
        },
    )
    db.commit()
    return [_event_out(e) for e in rows]


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventPatch,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    event = db.scalar(
        select(Event)
        .options(joinedload(Event.device), joinedload(Event.handler))
        .where(Event.id == event_id)
    )
    if event is None:
        raise HTTPException(404, "Событие не найдено")

    event.status = body.status
    if body.status == "new":
        event.handler = None
        event.handled_at = None
    else:
        event.handler = user
        event.handled_at = utcnow()
    _audit(db, user, "update_event", request, {"event_id": event_id, "status": body.status})
    db.commit()

    out = _event_out(event)
    background.add_task(hub.broadcast, {"type": "event_updated", "event": out.model_dump(mode="json")})
    return out


@router.get("/audit-log", response_model=list[AuditOut])
def audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AccessLog).options(joinedload(AccessLog.user)).order_by(AccessLog.id.desc()).limit(limit)
    ).all()
    _audit(db, user, "view_audit_log", request)
    db.commit()
    return [
        AuditOut(
            id=r.id,
            user_email=r.user.email,
            action=r.action,
            details=r.details,
            ip=r.ip,
            created_at=r.created_at,
        )
        for r in rows
    ]