"""Small in-memory TTL cache so we don't overload / hammer the public data providers."""
import asyncio
import time
from typing import Any, Awaitable, Callable

_store: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


async def cached(key: str, ttl: float, loader: Callable[[], Awaitable[Any]]) -> Any:
    hit = _store.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # only one request fetches a given key at a time
        hit = _store.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        value = await loader()
        _store[key] = (time.time() + ttl, value)
        return value


def clear() -> None:
    _store.clear()
