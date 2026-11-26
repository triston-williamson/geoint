"""USGS real-time earthquake feed (GeoJSON, no key needed)."""
import time

import httpx

from . import feature

BASE = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"


def _file(days: int) -> str:
    return "all_day.geojson" if days <= 1 else "all_week.geojson" if days <= 7 else "all_month.geojson"


def parse(data: dict, days: int, min_mag: float) -> list[dict]:
    cutoff = (time.time() - days * 86400) * 1000
    out = []
    for f in data.get("features", []):
        p = f["properties"]
        mag = p.get("mag")
        if mag is None or mag < min_mag or p["time"] < cutoff:
            continue
        lon, lat, depth = f["geometry"]["coordinates"][:3]
        epoch = int(p["time"])
        out.append(
            feature(
                lon,
                lat,
                source="quakes",
                id=f"quake-{f['id']}",
                time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch / 1000)),
                epoch=epoch,
                title=f"M{mag:.1f} · {p.get('place') or 'Unknown location'}",
                severity=round(min(max((mag - 2) / 5, 0), 1), 3),
                url=p.get("url"),
                mag=mag,
                depth_km=depth,
                tsunami=bool(p.get("tsunami")),
                alert=p.get("alert"),
            )
        )
    return out


async def fetch(client: httpx.AsyncClient, days: int = 1, min_mag: float = 2.5):
    resp = await client.get(BASE + _file(days))
    resp.raise_for_status()
    return parse(resp.json(), days, min_mag), {"file": _file(days)}
