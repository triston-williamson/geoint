"""NASA FIRMS active fire detections (VIIRS on NOAA-20).

With FIRMS_MAP_KEY set, uses the area API (1-5 days, worldwide).
Without a key, falls back to the open 24h / 48h / 7d global CSV files.
"""
import io
from datetime import datetime, timezone

import httpx
import pandas as pd

from .. import config
from . import feature, iso_and_epoch

OPEN_FILES = {
    1: "J1_VIIRS_C2_Global_24h.csv",
    2: "J1_VIIRS_C2_Global_48h.csv",
    7: "J1_VIIRS_C2_Global_7d.csv",
}
OPEN_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/"
API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
MAX_POINTS = 25_000  # keep the browser responsive; strongest fires are kept


def _url(days: int) -> tuple[str, str]:
    if config.FIRMS_MAP_KEY:
        d = max(1, min(days, 5))
        return f"{API_BASE}/{config.FIRMS_MAP_KEY}/VIIRS_NOAA20_NRT/world/{d}", "api"
    bucket = 1 if days <= 1 else 2 if days <= 2 else 7
    return OPEN_BASE + OPEN_FILES[bucket], "open-file"


def parse(csv_text: str, days: int) -> list[dict]:
    df = pd.read_csv(io.StringIO(csv_text))
    if df.empty:
        return []
    conf = df["confidence"].astype(str).str.lower().str[0]  # 'l' / 'n' / 'h'
    df = df[conf.isin(["n", "h"])].copy()
    times = pd.to_datetime(
        df["acq_date"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4),
        format="%Y-%m-%d %H%M",
        utc=True,
    )
    df["ts"] = times
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    df = df[df["ts"] >= cutoff]
    df = df.nlargest(MAX_POINTS, "frp")

    out = []
    for i, r in enumerate(df.itertuples(index=False)):
        iso, epoch = iso_and_epoch(r.ts.to_pydatetime())
        frp = float(r.frp)
        out.append(
            feature(
                float(r.longitude),
                float(r.latitude),
                source="fires",
                id=f"fire-{epoch}-{i}",
                time=iso,
                epoch=epoch,
                title=f"Fire · {frp:.0f} MW radiative power",
                severity=round(min(frp / 150.0, 1.0), 3),
                url=None,
                frp=frp,
                confidence=str(r.confidence),
                daynight=str(r.daynight),
                satellite=str(r.satellite),
            )
        )
    return out


async def fetch(client: httpx.AsyncClient, days: int = 1) -> tuple[list[dict], dict]:
    url, mode = _url(days)
    resp = await client.get(url)
    resp.raise_for_status()
    text = resp.text
    if text.lstrip().lower().startswith(("invalid", "error")):
        raise RuntimeError(f"FIRMS rejected the request: {text[:120]}")
    feats = parse(text, days)
    return feats, {"mode": mode, "fetched": datetime.now(timezone.utc).isoformat()}
