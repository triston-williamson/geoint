"""Offline tests for the spatial analysis."""
from app.analysis import exposure, hotspots
from app.feeds import feature


def pt(lon, lat, source, sev=0.5, epoch=1):
    return feature(lon, lat, source=source, id=f"{source}-{lon}-{lat}", time=None, epoch=epoch, title=source, severity=sev)


def test_multi_source_cluster_ranks_first():
    # cluster A: 6 fires only. cluster B: 3 fires + 3 news in the same place
    a = [pt(10 + i * 0.01, 10, "fires") for i in range(6)]
    b = [pt(50 + i * 0.01, -5, "fires") for i in range(3)] + [pt(50 + i * 0.01, -5.01, "news") for i in range(3)]
    result = hotspots(a + b, eps_km=20, min_samples=3)
    assert len(result) == 2
    assert set(result[0]["sources"]) == {"fires", "news"}


def test_noise_is_ignored():
    scattered = [pt(i * 20, 0, "quakes") for i in range(8)]
    assert hotspots(scattered, eps_km=50, min_samples=3) == []


def test_exposure_distance():
    site = feature(0, 0, source="infra", id="plant", time=None, epoch=None, title="Plant", severity=0.5)
    near = pt(0.05, 0, "fires")  # ~5.6 km east
    far = pt(1, 0, "fires")  # ~111 km east
    out = exposure([site], [near, far], radius_km=10)
    assert len(out) == 1
    p = out[0]["properties"]
    assert p["hazards_nearby"] == 1
    assert 5 < p["nearest_km"] < 6.5
