"""Простейший ограничитель частоты запросов (в памяти процесса)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(name: str, max_calls: int, per_seconds: int):
    def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        queue = _hits[f"{name}:{ip}"]
        now = time.monotonic()
        while queue and now - queue[0] > per_seconds:
            queue.popleft()
        if len(queue) >= max_calls:
            raise HTTPException(429, "Слишком много попыток. Повторите позже.")
        queue.append(now)

    return dependency