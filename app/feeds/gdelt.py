"""GDELT 2.0 event exports: geolocated news events, published every 15 minutes.

GDELT sometimes skips a 15-minute file, so missing files are ignored.
Events geocoded only to a country centroid (ActionGeo_Type == 1) are dropped,
because they would create false "hotspots" in the middle of countries.
"""
import asyncio
import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

import httpx

from . import feature, iso_and_epoch

BASE = "https://data.gdeltproject.org/gdeltv2/"

# CAMEO QuadClass: 1 verbal cooperation, 2 material cooperation,
#                  3 verbal conflict,    4 material conflict
QUAD_LABELS = {1: "Verbal cooperation", 2: "Material cooperation", 3: "Verbal conflict", 4: "Material conflict"}

# Column indexes in the 61-column export table
C_ID, C_ACTOR1, C_ACTOR2 = 0, 6, 16
C_CODE, C_ROOT, C_QUAD, C_GOLD, C_MENTIONS = 26, 28, 29, 30, 31
C_TONE, C_GEOTYPE, C_GEONAME, C_LAT, C_LON, C_ADDED, C_URL = 34, 51, 52, 56, 57, 59, 60


def _slots(latest: datetime, n: int) -> list[str]:
    return [(latest - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(n)]


def parse_export(raw_zip: bytes, conflict_only: bool) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
    out = []
    for row in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(row) < 61 or not row[C_LAT] or not row[C_LON]:
            continue
        if row[C_GEOTYPE] in ("", "1"):
            continue
        quad = int(row[C_QUAD] or 0)
        if conflict_only and quad < 3:
            continue
        try:
            lat, lon = float(row[C_LAT]), float(row[C_LON])
            dt = datetime.strptime(row[C_ADDED], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        iso, epoch = iso_and_epoch(dt)
        gold = float(row[C_GOLD] or 0)
        mentions = int(row[C_MENTIONS] or 0)
        actors = " → ".join(a for a in (row[C_ACTOR1], row[C_ACTOR2]) if a) or "Unnamed actors"
        out.append(
            feature(
                lon,
                lat,
                source="news",
                id=f"news-{row[C_ID]}",
                time=iso,
                epoch=epoch,
                title=f"{QUAD_LABELS.get(quad, 'Event')} · {actors}",
                # Goldstein runs -10 (most destabilising) .. +10; weight by coverage
                severity=round(min(max(-gold, 0) / 10 * 0.7 + min(mentions, 30) / 30 * 0.3, 1), 3),
                url=row[C_URL] or None,
                place=row[C_GEONAME],
                quad_class=quad,
                cameo=row[C_CODE],
                goldstein=gold,
                mentions=mentions,
                tone=round(float(row[C_TONE] or 0), 2),
            )
        )
    return out


async def fetch(client: httpx.AsyncClient, hours: int = 3, conflict_only: bool = True):
    resp = await client.get(BASE + "lastupdate.txt")
    resp.raise_for_status()
    stamp = resp.text.split()[2].rsplit("/", 1)[1].split(".")[0]
    latest = datetime.strptime(stamp, "%Y%m%d%H%M%S")
    slots = _slots(latest, max(1, min(hours, 24)) * 4)

    sem = asyncio.Semaphore(6)

    async def one(slot: str):
        async with sem:
            r = await client.get(f"{BASE}{slot}.export.CSV.zip")
            if r.status_code != 200 or not r.content:
                return None
            return await asyncio.to_thread(parse_export, r.content, conflict_only)

    results = await asyncio.gather(*(one(s) for s in slots), return_exceptions=True)
    feats, seen, missing = [], set(), 0
    for res in results:
        if not isinstance(res, list):
            missing += 1
            continue
        for f in res:
            if f["properties"]["id"] not in seen:
                seen.add(f["properties"]["id"])
                feats.append(f)
    return feats, {"files_requested": len(slots), "files_missing": missing, "latest": stamp}
