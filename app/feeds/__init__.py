"""Data feeds. Each one returns a list of GeoJSON Features in a shared schema:

properties = {
    "source":   "fires" | "quakes" | "news" | "infra",
    "id":       unique string,
    "time":     ISO-8601 UTC string (None for static infrastructure),
    "epoch":    milliseconds since epoch (None for static infrastructure),
    "title":    short human-readable label,
    "severity": 0..1 normalised importance (used for marker size),
    "url":      link to the original record, if any,
    ...source-specific extras
}
"""
from datetime import datetime, timezone


def feature(lon: float, lat: float, **props) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
        "properties": props,
    }


def iso_and_epoch(dt: datetime) -> tuple[str, int]:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), int(dt.timestamp() * 1000)


def collection(features: list[dict], **meta) -> dict:
    return {"type": "FeatureCollection", "features": features, "meta": meta}
