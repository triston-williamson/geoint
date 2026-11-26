"""Spatial analysis: multi-source hotspot clustering and infrastructure exposure."""
import math
from collections import Counter

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree

EARTH_KM = 6371.0088


def _coords_rad(features: list[dict]) -> np.ndarray:
    # BallTree / DBSCAN haversine metric expects [lat, lon] in radians
    pts = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in features]
    return np.radians(np.array(pts, dtype=float)).reshape(-1, 2)


def hotspots(features: list[dict], eps_km: float = 50, min_samples: int = 5, top: int = 40) -> list[dict]:
    """Cluster events from all sources. Clusters where several feeds coincide rank highest.

    score = (distinct sources)^2 * log(1 + events) * (1 + mean severity)
    """
    if len(features) < min_samples:
        return []
    X = _coords_rad(features)
    labels = DBSCAN(
        eps=eps_km / EARTH_KM, min_samples=min_samples, metric="haversine", algorithm="ball_tree"
    ).fit_predict(X)

    clusters = []
    for label in set(labels) - {-1}:
        idx = np.where(labels == label)[0]
        members = [features[i] for i in idx]
        lat = np.degrees(X[idx, 0])
        lon = np.degrees(X[idx, 1])
        sources = Counter(m["properties"]["source"] for m in members)
        sev = float(np.mean([m["properties"].get("severity") or 0 for m in members]))
        epochs = [m["properties"]["epoch"] for m in members if m["properties"].get("epoch")]
        score = len(sources) ** 2 * math.log1p(len(members)) * (1 + sev)
        # top 3 headlines/labels by severity, for the sidebar
        sample = sorted(members, key=lambda m: m["properties"].get("severity") or 0, reverse=True)[:3]
        clusters.append(
            {
                "id": f"hs-{label}",
                "center": [round(float(lon.mean()), 4), round(float(lat.mean()), 4)],
                "bbox": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
                "count": len(members),
                "sources": dict(sources),
                "mean_severity": round(sev, 3),
                "first_epoch": min(epochs) if epochs else None,
                "last_epoch": max(epochs) if epochs else None,
                "score": round(score, 2),
                "examples": [m["properties"]["title"] for m in sample],
            }
        )
    clusters.sort(key=lambda c: c["score"], reverse=True)
    return clusters[:top]


def exposure(infra: list[dict], hazards: list[dict], radius_km: float = 10) -> list[dict]:
    """For each infrastructure site, find hazards within radius_km. Returns exposed sites only,
    nearest first, with the distance and number of hazards nearby."""
    if not infra or not hazards:
        return []
    tree = BallTree(_coords_rad(hazards), metric="haversine")
    X = _coords_rad(infra)
    r = radius_km / EARTH_KM
    idx_lists, dist_lists = tree.query_radius(X, r=r, return_distance=True, sort_results=True)

    exposed = []
    for site, idxs, dists in zip(infra, idx_lists, dist_lists):
        if len(idxs) == 0:
            continue
        nearest = hazards[int(idxs[0])]["properties"]
        sources = Counter(hazards[int(i)]["properties"]["source"] for i in idxs)
        props = dict(site["properties"])
        props.update(
            nearest_km=round(float(dists[0]) * EARTH_KM, 2),
            hazards_nearby=int(len(idxs)),
            hazard_sources=dict(sources),
            nearest_hazard=nearest["title"],
        )
        exposed.append({**site, "properties": props})
    exposed.sort(key=lambda f: f["properties"]["nearest_km"])
    return exposed
