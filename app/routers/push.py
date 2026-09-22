from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import current_staff
from ..models import PushSubscription, User
from ..schemas import PushSubscribeIn, PushUnsubscribeIn

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/public-key")
def public_key():
    return {"enabled": settings.push_enabled, "public_key": settings.vapid_public_key}


@router.post("/subscribe", status_code=204)
def subscribe(body: PushSubscribeIn, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    if not body.endpoint.startswith("https://"):
        raise HTTPException(422, "Некорректный адрес подписки")
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub:
        sub.user_id, sub.p256dh, sub.auth = user.id, body.keys.p256dh, body.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth
            )
        )
    db.commit()


@router.post("/unsubscribe", status_code=204)
def unsubscribe(body: PushUnsubscribeIn, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id
        )
    )
    db.commit()