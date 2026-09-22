"""Доставка тревог: WebSocket-дашборд, Telegram (дублирующий канал), Web Push."""
import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete

from ..config import settings
from ..database import SessionLocal
from ..models import PushSubscription
from ..ws import hub

log = logging.getLogger("antibullying.notify")


def _local_time(iso: str) -> str:
    try:
        tz = ZoneInfo(settings.display_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.fromisoformat(iso).astimezone(tz).strftime("%d.%m %H:%M:%S")


async def send_telegram(event: dict) -> None:
    if not settings.telegram_enabled:
        return
    text = (
        "⚠️ Возможный буллинг\n"
        f"Локация: {event['device_location']}\n"
        f"Триггер: «{event['trigger_word']}» (уверенность {event['confidence']:.0%})\n"
        f"Время: {_local_time(event['occurred_at'])}"
    )
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": text})
            resp.raise_for_status()
    except Exception as exc:
        log.warning("Telegram: не удалось отправить (%s)", type(exc).__name__)


def _push_sync(subs: list[dict], data: str) -> list[int]:
    from pywebpush import WebPushException, webpush

    dead: list[int] = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=data,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_contact},
                ttl=120,
            )
        except WebPushException as exc:
            code = getattr(exc.response, "status_code", None)
            if code in (404, 410):
                dead.append(sub["id"])
            else:
                log.warning("Web Push: ошибка (%s)", code)
        except Exception as exc:
            log.warning("Web Push: ошибка (%s)", type(exc).__name__)
    if dead:
        with SessionLocal() as db:
            db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
            db.commit()
    return dead


async def send_push(event: dict, subs: list[dict]) -> None:
    if not (settings.push_enabled and subs):
        return
    data = json.dumps(
        {
            "title": f"⚠️ {event['device_location']}",
            "body": f"Слово-триггер: «{event['trigger_word']}»",
            "tag": f"ab-event-{event['id']}",
            "event_id": event["id"],
        },
        ensure_ascii=False,
    )
    await asyncio.to_thread(_push_sync, subs, data)


async def dispatch_alert(event: dict, subs: list[dict]) -> None:
    await asyncio.gather(
        hub.broadcast({"type": "event", "event": event}),
        send_telegram(event),
        send_push(event, subs),
        return_exceptions=True,
    )