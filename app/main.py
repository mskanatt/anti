"""Anti-Bullying System — точка входа.

Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, SessionLocal, engine
from .models import AccessLog, User
from .routers import auth, devices, events, push
from .security import decode_jwt
from .ws import hub

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Anti-Bullying System", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    return response


app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(events.router)
app.include_router(push.router)


def _authorize_staff_ws(token: str, ip: str | None) -> bool:
    try:
        payload = decode_jwt(token)
    except jwt.PyJWTError:
        return False
    if payload.get("role") != "staff":
        return False
    with SessionLocal() as db:
        user = db.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            return False
        db.add(AccessLog(user_id=user.id, action="open_live_feed", ip=ip))
        db.commit()
    return True


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=5)
        token = first.get("token") if isinstance(first, dict) else None
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        await ws.close(code=4401)
        return
    ip = ws.client.host if ws.client else None
    if not isinstance(token, str) or not await run_in_threadpool(_authorize_staff_ws, token, ip):
        await ws.close(code=4401)
        return

    await ws.send_json({"type": "ready"})
    hub.add(ws)
    try:
        while True:
            message = await ws.receive_text()
            if message == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        hub.discard(ws)


@app.get("/", include_in_schema=False)
def page_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def page_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/device", include_in_schema=False)
def page_device():
    return FileResponse(STATIC_DIR / "device.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")