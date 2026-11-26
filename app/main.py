"""GEOINT event fusion dashboard: FastAPI backend.

Run:  uvicorn app.main:app --reload   (or press F5 in VS Code)
Open: http://127.0.0.1:8000
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis, config
from .cache import cached
from .feeds import collection, firms, gdelt, osm, usgs

http: httpx.AsyncClient | None = None
status: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    global http
    http = httpx.AsyncClient(
        timeout=config.HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": config.USER_AGENT}
    )
    yield
    await http.aclose()


app = FastAPI(title="GEOINT Event Fusion", lifespan=lifespan)


async def _load(name: str, key: str, fn, *args, ttl: float | None = None):
    """Fetch through the cache, record feed health, and turn failures into clean HTTP errors."""
    try:
        feats, meta = await cached(key, ttl or config.CACHE_TTL_SECONDS, lambda: fn(http, *args))
        status[name] = {"ok": True, "count": len(feats), "checked": _now(), **meta}
        return feats, meta
    except ValueError as exc:  # bad request from the user (e.g. area too big)
        raise HTTPException(400, str(exc))
    except Exception as exc:  # upstream problem
        status[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300], "checked": _now()}
        raise HTTPException(502, f"{name} feed unavailable: {exc}")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        w, s, e, n = (float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be 'west,south,east,north'")
    return s, w, n, e


def _in_window(feats: list[dict], start: int | None, end: int | None) -> list[dict]:
    if start is None and end is None:
        return feats
    lo, hi = start or 0, end or 10**15
    return [f for f in feats if f["properties"].get("epoch") and lo <= f["properties"]["epoch"] <= hi]


# The feeds section handles fetching and returning data from various sources like fires, quakes, and news.

async def get_fires(days: int):
    return await _load("fires", f"fires:{days}", firms.fetch, days)


async def get_quakes(days: int, min_mag: float):
    return await _load("quakes", f"quakes:{days}:{min_mag}", usgs.fetch, days, min_mag)


async def get_news(hours: int, conflict_only: bool):
    return await _load("news", f"news:{hours}:{conflict_only}", gdelt.fetch, hours, conflict_only)


@app.get("/api/feeds/fires")
async def fires(days: int = Query(1, ge=1, le=7)):
    feats, meta = await get_fires(days)
    return collection(feats, **meta)


@app.get("/api/feeds/quakes")
async def quakes(days: int = Query(1, ge=1, le=30), min_mag: float = Query(2.5, ge=0, le=9)):
    feats, meta = await get_quakes(days, min_mag)
    return collection(feats, **meta)


@app.get("/api/feeds/news")
async def news(hours: int = Query(3, ge=1, le=24), conflict_only: bool = True):
    feats, meta = await get_news(hours, conflict_only)
    return collection(feats, **meta)


@app.get("/api/feeds/infra")
async def infra(kind: str = "power", bbox: str = Query(..., description="west,south,east,north")):
    s, w, n, e = _parse_bbox(bbox)
    key = f"infra:{kind}:{s:.2f},{w:.2f},{n:.2f},{e:.2f}"
    feats, meta = await _load("infra", key, osm.fetch, kind, s, w, n, e, ttl=3600)
    return collection(feats, **meta)


# The analysis section handles performing spatial analysis on the collected feed data, such as hotspot detection.

@app.get("/api/hotspots")
async def hotspot_analysis(
    days: int = Query(1, ge=1, le=7),
    news_hours: int = Query(3, ge=1, le=24),
    min_mag: float = 2.5,
    eps_km: float = Query(50, gt=0, le=500),
    min_samples: int = Query(5, ge=2, le=500),
    start: int | None = None,
    end: int | None = None,
    sources: str = "fires,quakes,news",
):
    wanted = set(sources.split(","))
    feats: list[dict] = []
    errors = []
    for name, loader in (
        ("fires", lambda: get_fires(days)),
        ("quakes", lambda: get_quakes(days, min_mag)),
        ("news", lambda: get_news(news_hours, True)),
    ):
        if name not in wanted:
            continue
        try:
            f, _ = await loader()
            feats.extend(f)
        except HTTPException as exc:
            errors.append(exc.detail)
    feats = _in_window(feats, start, end)
    return {"hotspots": analysis.hotspots(feats, eps_km, min_samples), "events_used": len(feats), "errors": errors}


@app.get("/api/exposure")
async def exposure_analysis(
    bbox: str,
    kind: str = "power",
    radius_km: float = Query(10, gt=0, le=200),
    days: int = Query(1, ge=1, le=7),
    hazards: str = "fires,quakes",
    min_mag: float = 2.5,
    start: int | None = None,
    end: int | None = None,
):
    s, w, n, e = _parse_bbox(bbox)
    sites, _ = await _load("infra", f"infra:{kind}:{s:.2f},{w:.2f},{n:.2f},{e:.2f}", osm.fetch, kind, s, w, n, e, ttl=3600)
    hz: list[dict] = []
    if "fires" in hazards:
        hz += (await get_fires(days))[0]
    if "quakes" in hazards:
        hz += (await get_quakes(days, min_mag))[0]
    if "news" in hazards:
        hz += (await get_news(3, True))[0]
    hz = _in_window(hz, start, end)
    exposed = analysis.exposure(sites, hz, radius_km)
    return {
        **collection(exposed, kind=kind, radius_km=radius_km),
        "sites_checked": len(sites),
        "hazards_checked": len(hz),
    }


@app.get("/api/status")
async def feed_status():
    return {"firms_key": bool(config.FIRMS_MAP_KEY), "feeds": status}


# The front end section handles serving the main HTML page and static assets like JavaScript and CSS.

@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
