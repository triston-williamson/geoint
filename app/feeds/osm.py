"""OpenStreetMap critical infrastructure via the Overpass API (bbox queries only)."""
import httpx

from .. import config
from . import feature

# kind -> list of Overpass tag filters
KINDS = {
    "power": ['["power"="plant"]', '["power"="substation"]["voltage"~"^[0-9]{6}"]'],
    "health": ['["amenity"="hospital"]'],
    "airports": ['["aeroway"="aerodrome"]["iata"]'],
    "ports": ['["industrial"="port"]', '["harbour"="yes"]', '["landuse"="port"]'],
    "fuel": ['["man_made"="storage_tank"]["content"~"oil|fuel|gas"]', '["industrial"="refinery"]'],
}
MAX_BBOX_DEG2 = 30.0  # roughly 5.5°x5.5°; bigger areas are too slow for the public Overpass server


def bbox_area(s: float, w: float, n: float, e: float) -> float:
    return abs(n - s) * abs(e - w)


def build_query(kind: str, s: float, w: float, n: float, e: float) -> str:
    box = f"({s},{w},{n},{e})"
    parts = "".join(f"nwr{tag}{box};" for tag in KINDS[kind])
    return f"[out:json][timeout:90];({parts});out center tags 3000;"


def parse(data: dict, kind: str) -> list[dict]:
    out = []
    for el in data.get("elements", []):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("operator") or f"Unnamed {kind} site"
        detail = tags.get("plant:source") or tags.get("power") or tags.get("amenity") or tags.get("aeroway") or ""
        out.append(
            feature(
                lon,
                lat,
                source="infra",
                id=f"osm-{el['type']}-{el['id']}",
                time=None,
                epoch=None,
                title=f"{name}" + (f" · {detail}" if detail else ""),
                severity=0.5,
                url=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                kind=kind,
                tags={k: v for k, v in tags.items() if not k.startswith(("source", "note", "fixme"))},
            )
        )
    return out


async def fetch(client: httpx.AsyncClient, kind: str, s: float, w: float, n: float, e: float):
    if kind not in KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Choose one of: {', '.join(KINDS)}")
    if bbox_area(s, w, n, e) > MAX_BBOX_DEG2:
        raise ValueError("Area too large for an infrastructure query. Zoom in further.")
    resp = await client.post(
        config.OVERPASS_URL,
        data={"data": build_query(kind, s, w, n, e)},
        headers={"User-Agent": config.USER_AGENT},
        timeout=95,  # Overpass can take 30-60 s for a dense region
    )
    resp.raise_for_status()
    return parse(resp.json(), kind), {"kind": kind}
