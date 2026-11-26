# GEOINT Event Fusion Dashboard

A map that combines open-source event feeds, finds multi-source hotspots, and checks which
critical infrastructure sits near the active hazards.

| Feed | Source | Key needed? |
|---|---|---|
| Active fires | NASA FIRMS (VIIRS NOAA-20) | Optional (`FIRMS_MAP_KEY`) |
| Earthquakes | USGS real-time GeoJSON | No |
| News events | GDELT 2.0 event exports (15-min updates) | No |
| Infrastructure | OpenStreetMap via Overpass API | No |

## Setup (once)

```bash
cd ~/geoint
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then paste your FIRMS key into .env
```

Open the folder in VS Code (`code ~/geoint`). When asked, pick the `.venv` interpreter
(or Cmd+Shift+P → "Python: Select Interpreter" → `.venv`).

## Run

- **VS Code:** press **F5** ("GEOINT dashboard (uvicorn)"), then open http://127.0.0.1:8000
- **Terminal:** `.venv/bin/uvicorn app.main:app --reload`
- **Tests:** `.venv/bin/pytest -q` (or the Testing panel in VS Code)

## Using it

1. **Data range:** you can choose how far back to load fires/quakes (24 h to 7 days) and news (1 to 12 h), then press the *Load data*.
2. **Timeline:** drag the slider to move through time. Set *Window* to (for example) 6 h and press *Play* to animate the selected timeframe.
3. **Hotspots:** clusters events from every feed (DBSCAN, haversine distance) within the current time window.
   Score = (distinct feeds)² × log(1 + events) × (1 + mean severity), so places where fires *and* news *and*
   quakes coincide rank above a large single-source cluster. Click a result to zoom in and access the news article / event.
4. **Infrastructure exposure:** zoom to a region (≤ about 5°×5° or a little less than a states size), pick a site type and radius, and press *Analyze current view*. Sites with hazards inside the radius get a red ring. Overpass queries can take up to about a minute to load the data / information.

Click any point for details and a link to the source record.

## Project layout

```
app/
  main.py        FastAPI routes + serves the front end
  analysis.py    hotspot clustering and exposure (scikit-learn BallTree/DBSCAN)
  cache.py       in-memory TTL cache (default 10 min)
  config.py      settings from .env
  feeds/         one module per data source, all output the same GeoJSON schema
static/          index.html, app.js (MapLibre GL), style.css
tests/           offline unit tests for the analysis
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/feeds/fires?days=1` | FIRMS fires (high/nominal confidence, strongest 25k) |
| `GET /api/feeds/quakes?days=1&min_mag=2.5` | USGS earthquakes |
| `GET /api/feeds/news?hours=3&conflict_only=true` | GDELT events (country-centroid geocodes removed) |
| `GET /api/feeds/infra?kind=power&bbox=w,s,e,n` | OSM sites: `power`, `health`, `airports`, `ports`, `fuel` |
| `GET /api/hotspots?eps_km=50&min_samples=5&start=&end=` | Multi-source clusters |
| `GET /api/exposure?bbox=w,s,e,n&kind=power&radius_km=10` | Infrastructure near hazards |
| `GET /api/status` | Feed health |

Interactive API docs: http://127.0.0.1:8000/docs

## Notes and limits

- Without a FIRMS key the app uses the open 24h/48h/7d files. With a key it uses the FIRMS API (up to 5 days).
- GDELT occasionally skips a 15-minute file. Missing files are ignored and counted in `/api/status`.
- GDELT locations are where a story says an event happened, geocoded automatically. Treat them as leads, not ground truth.
- The public Overpass server is shared. Keep queries to regional areas.

## Ideas for next steps

- Persist history in SQLite/DuckDB to track trends beyond each feed's window
- Add feeds: NOAA weather alerts, ACLED conflict data, OpenSky aircraft, NASA EONET
- Alerts: notify when a new hotspot appears near a watch-list area
- Sentinel-2 before/after imagery for a selected hotspot
