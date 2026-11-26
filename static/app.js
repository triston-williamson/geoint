/* GEOINT Event Fusion: front end (MapLibre GL, no build step). */
"use strict";

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const FEEDS = {
  fires:  { label: "Active fires (NASA FIRMS)", color: css("--fires"),  timed: true },
  quakes: { label: "Earthquakes (USGS)",        color: css("--quakes"), timed: true },
  news:   { label: "News events (GDELT)",       color: css("--news"),   timed: true },
};
const OVERLAYS = {
  hotspots: { label: "Hotspots",       color: css("--hotspot") },
  infra:    { label: "Infrastructure", color: css("--infra") },
};

const state = { data: {}, minEpoch: null, maxEpoch: null, playTimer: null };

// ---------- helpers ----------
function toast(msg, isError = false, ms = 3500) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "show" + (isError ? " error" : "");
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.className = ""), ms);
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function safeUrl(u) {
  return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null;
}
function fmtTime(ms) {
  return new Date(ms).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}
async function getJSON(url) {
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status} ${r.statusText}`);
  return body;
}
const empty = () => ({ type: "FeatureCollection", features: [] });

// ---------- map ----------
const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  center: [10, 20],
  zoom: 1.6,
  attributionControl: { compact: true },
});
// keep the canvas matched to its container (window resizes, late layout)
new ResizeObserver(() => map.resize()).observe($("map"));
map.addControl(new maplibregl.NavigationControl(), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

map.on("load", () => {
  // event layers: radius grows with severity and zoom
  for (const [name, cfg] of Object.entries(FEEDS)) {
    map.addSource(name, { type: "geojson", data: empty() });
    map.addLayer({
      id: name,
      type: "circle",
      source: name,
      paint: {
        "circle-color": cfg.color,
        "circle-opacity": name === "fires" ? 0.75 : 0.85,
        "circle-stroke-color": "#000",
        "circle-stroke-width": name === "fires" ? 0 : 0.6,
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          1, ["+", 1.5, ["*", 4, ["get", "severity"]]],
          8, ["+", 4, ["*", 10, ["get", "severity"]]],
        ],
      },
    });
  }

  map.addSource("infra", { type: "geojson", data: empty() });
  map.addLayer({
    id: "infra",
    type: "circle",
    source: "infra",
    paint: {
      "circle-color": css("--infra"),
      "circle-radius": ["case", ["has", "nearest_km"], 7, 4],
      "circle-stroke-color": ["case", ["has", "nearest_km"], css("--exposed"), "#000"],
      "circle-stroke-width": ["case", ["has", "nearest_km"], 3, 0.8],
    },
  });

  map.addSource("hotspots", { type: "geojson", data: empty() });
  map.addLayer({
    id: "hotspots",
    type: "circle",
    source: "hotspots",
    paint: {
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": css("--hotspot"),
      "circle-stroke-width": 2,
      "circle-radius": ["interpolate", ["linear"], ["get", "score"], 1, 10, 30, 34],
    },
  });
  map.addLayer({
    id: "hotspots-label",
    type: "symbol",
    source: "hotspots",
    layout: { "text-field": ["to-string", ["get", "rank"]], "text-size": 12, "text-font": ["Open Sans Bold"] },
    paint: { "text-color": css("--hotspot"), "text-halo-color": "#000", "text-halo-width": 1.2 },
  });

  for (const id of ["fires", "quakes", "news", "infra", "hotspots"]) {
    map.on("click", id, (e) => showPopup(e.features[0], e.lngLat));
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
  }

  buildLayerList();
  loadAll();
  refreshStatus();
  setInterval(refreshStatus, 30000);
});

// ---------- popups ----------
function showPopup(f, lngLat) {
  const p = f.properties;
  const rows = [];
  const add = (k, v) => v !== undefined && v !== null && v !== "" && rows.push(`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`);

  let title = p.title;
  if (f.layer.id === "hotspots") {
    title = `Hotspot #${p.rank}`;
    add("Events", p.count);
    add("Sources", p.sources_text);
    add("Score", p.score);
    add("Window", p.window_text);
  } else {
    add("Time", p.time ? fmtTime(p.epoch) : null);
    add("Magnitude", p.mag);
    add("Depth (km)", p.depth_km);
    add("FRP (MW)", p.frp);
    add("Confidence", p.confidence);
    add("Place", p.place);
    add("Goldstein", p.goldstein);
    add("Mentions", p.mentions);
    add("Tone", p.tone);
    add("Nearest hazard", p.nearest_km != null ? `${p.nearest_km} km · ${p.nearest_hazard}` : null);
    add("Hazards in radius", p.hazards_nearby);
  }
  add("Lat, lon", f.geometry.coordinates.slice().reverse().map((c) => c.toFixed(4)).join(", "));
  const url = safeUrl(p.url);
  const link = url ? `<p><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open source record ↗</a></p>` : "";
  new maplibregl.Popup({ maxWidth: "320px" })
    .setLngLat(lngLat)
    .setHTML(`<div class="popup"><h3>${esc(title)}</h3><dl>${rows.join("")}</dl>${link}</div>`)
    .addTo(map);
}

// ---------- layer list ----------
function buildLayerList() {
  const ul = $("layers");
  ul.innerHTML = "";
  for (const [id, cfg] of Object.entries({ ...FEEDS, ...OVERLAYS })) {
    const li = document.createElement("li");
    li.innerHTML = `<input type="checkbox" id="lyr-${id}" checked>
      <span class="swatch" style="background:${cfg.color}"></span>
      <label for="lyr-${id}" class="check">${esc(cfg.label)}</label>
      <span class="count" id="count-${id}">–</span>`;
    li.querySelector("input").addEventListener("change", (e) => {
      const vis = e.target.checked ? "visible" : "none";
      map.setLayoutProperty(id, "visibility", vis);
      if (id === "hotspots") map.setLayoutProperty("hotspots-label", "visibility", vis);
    });
    ul.appendChild(li);
  }
}
function setCount(id, n) {
  const el = $(`count-${id}`);
  if (el) el.textContent = n == null ? "–" : n.toLocaleString();
}

// ---------- loading feeds ----------
function params() {
  return {
    days: $("days").value,
    newsHours: $("news-hours").value,
    minMag: $("min-mag").value,
    conflictOnly: $("conflict-only").checked,
  };
}
async function loadFeed(name) {
  const p = params();
  const url = {
    fires: `/api/feeds/fires?days=${p.days}`,
    quakes: `/api/feeds/quakes?days=${p.days}&min_mag=${p.minMag}`,
    news: `/api/feeds/news?hours=${p.newsHours}&conflict_only=${p.conflictOnly}`,
  }[name];
  setCount(name, null);
  try {
    const fc = await getJSON(url);
    state.data[name] = fc;
    map.getSource(name).setData(fc);
    setCount(name, fc.features.length);
  } catch (err) {
    state.data[name] = empty();
    map.getSource(name).setData(empty());
    toast(`${FEEDS[name].label}: ${err.message}`, true, 6000);
  }
}
async function loadAll() {
  const btn = $("reload");
  btn.disabled = true;
  btn.textContent = "Loading…";
  await Promise.all(Object.keys(FEEDS).map(loadFeed));
  btn.disabled = false;
  btn.textContent = "Load data";
  resetTimeline();
  refreshStatus();
}
$("reload").addEventListener("click", () => mapReady() && loadAll());

async function refreshStatus() {
  try {
    const s = await getJSON("/api/status");
    $("feed-status").innerHTML = ["fires", "quakes", "news", "infra"]
      .map((k) => {
        const f = s.feeds[k];
        const cls = !f ? "" : f.ok ? "ok" : "err";
        const tip = !f ? "not loaded yet" : f.ok ? `${f.count} items · ${f.checked}` : f.error;
        return `<span title="${esc(tip)}"><span class="dot ${cls}"></span>${k}</span>`;
      })
      .join("") + (s.firms_key ? "" : `<span title="Add FIRMS_MAP_KEY to .env for the FIRMS API">· open fire files</span>`);
  } catch { /* server restarting */ }
}

// ---------- timeline ----------
function resetTimeline() {
  let lo = Infinity, hi = -Infinity;
  for (const name of Object.keys(FEEDS)) {
    for (const f of state.data[name]?.features ?? []) {
      const e = f.properties.epoch;
      if (e < lo) lo = e;
      if (e > hi) hi = e;
    }
  }
  if (!isFinite(lo)) return;
  state.minEpoch = lo;
  state.maxEpoch = hi;
  $("time-end").value = 1000;
  applyTimeFilter();
}
function currentWindow() {
  if (state.minEpoch == null) return { start: null, end: null };
  const frac = $("time-end").value / 1000;
  const end = Math.round(state.minEpoch + frac * (state.maxEpoch - state.minEpoch));
  const hours = Number($("time-window").value);
  const start = hours ? end - hours * 3600e3 : state.minEpoch;
  return { start, end };
}
function applyTimeFilter() {
  const { start, end } = currentWindow();
  if (start == null) return;
  const filter = ["all", [">=", ["get", "epoch"], start], ["<=", ["get", "epoch"], end]];
  for (const name of Object.keys(FEEDS)) {
    map.setFilter(name, filter);
    const n = (state.data[name]?.features ?? []).filter((f) => f.properties.epoch >= start && f.properties.epoch <= end).length;
    setCount(name, n);
  }
  $("time-label").textContent = `${fmtTime(start).slice(5, 16)} → ${fmtTime(end).slice(5)}`;
}
$("time-end").addEventListener("input", applyTimeFilter);
$("time-window").addEventListener("change", applyTimeFilter);
$("play").addEventListener("click", () => {
  const btn = $("play");
  if (state.playTimer) {
    clearInterval(state.playTimer);
    state.playTimer = null;
    btn.textContent = "▶ Play";
    return;
  }
  if ($("time-window").value === "0") $("time-window").value = "6";
  const slider = $("time-end");
  if (Number(slider.value) >= 1000) slider.value = 0;
  btn.textContent = "❚❚ Pause";
  state.playTimer = setInterval(() => {
    slider.value = Math.min(1000, Number(slider.value) + 8);
    applyTimeFilter();
    if (Number(slider.value) >= 1000) btn.click();
  }, 120);
});

// ---------- hotspots ----------
const mapReady = () => !!map.getSource("hotspots") || (toast("Map is still loading, try again in a moment", true), false);

$("run-hotspots").addEventListener("click", async () => {
  if (!mapReady()) return;
  const btn = $("run-hotspots");
  const p = params();
  const { start, end } = currentWindow();
  const q = new URLSearchParams({
    days: p.days, news_hours: p.newsHours, min_mag: p.minMag,
    eps_km: $("eps").value, min_samples: $("min-samples").value,
  });
  if (start != null) { q.set("start", start); q.set("end", end); }
  btn.disabled = true;
  btn.textContent = "Clustering…";
  try {
    const res = await getJSON(`/api/hotspots?${q}`);
    const windowText = start != null ? `${fmtTime(start)} → ${fmtTime(end)}` : "all loaded data";
    const fc = {
      type: "FeatureCollection",
      features: res.hotspots.map((h, i) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: h.center },
        properties: {
          ...h, rank: i + 1, window_text: windowText,
          sources_text: Object.entries(h.sources).map(([k, v]) => `${k} ${v}`).join(", "),
        },
      })),
    };
    map.getSource("hotspots").setData(fc);
    setCount("hotspots", fc.features.length);
    renderHotspots(res.hotspots);
    if (res.errors.length) toast(res.errors.join(" · "), true, 6000);
    else toast(`${res.hotspots.length} hotspots from ${res.events_used.toLocaleString()} events`);
  } catch (err) {
    toast(`Hotspots: ${err.message}`, true, 6000);
  } finally {
    btn.disabled = false;
    btn.textContent = "Find hotspots in time window";
  }
});
function chips(sources) {
  const colors = { fires: FEEDS.fires.color, quakes: FEEDS.quakes.color, news: FEEDS.news.color };
  return Object.entries(sources)
    .map(([k, v]) => `<span class="chip" style="background:${colors[k] || "#999"}">${esc(k)} ${v}</span>`)
    .join("");
}
function renderHotspots(list) {
  const ol = $("hotspot-list");
  ol.innerHTML = "";
  list.forEach((h, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<div class="title">#${i + 1} · ${h.count} events · score ${h.score}</div>
      <div>${chips(h.sources)}</div>
      <div class="meta">${esc(h.examples[0] || "")}</div>`;
    li.addEventListener("click", () => {
      const [w, s, e, n] = h.bbox;
      if (e - w < 0.05 && n - s < 0.05) map.flyTo({ center: h.center, zoom: 10 });
      else map.fitBounds([[w, s], [e, n]], { padding: 80, maxZoom: 11 });
    });
    ol.appendChild(li);
  });
}

// ---------- infrastructure exposure ----------
$("run-exposure").addEventListener("click", async () => {
  if (!mapReady()) return;
  const btn = $("run-exposure");
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(4)).join(",");
  const hazards = [$("hz-fires").checked && "fires", $("hz-quakes").checked && "quakes"].filter(Boolean).join(",");
  if (!hazards) return toast("Pick at least one hazard type", true);
  const { start, end } = currentWindow();
  const p = params();
  const q = new URLSearchParams({
    bbox, kind: $("infra-kind").value, radius_km: $("radius").value,
    days: p.days, min_mag: p.minMag, hazards,
  });
  if (start != null) { q.set("start", start); q.set("end", end); }

  btn.disabled = true;
  btn.textContent = "Querying OpenStreetMap… (can take ~1 min)";
  $("exposure-summary").textContent = "";
  try {
    // show every site in view, then highlight the exposed ones
    const all = await getJSON(`/api/feeds/infra?kind=${q.get("kind")}&bbox=${bbox}`);
    const res = await getJSON(`/api/exposure?${q}`);
    const exposedIds = new Set(res.features.map((f) => f.properties.id));
    const merged = all.features.filter((f) => !exposedIds.has(f.properties.id)).concat(res.features);
    map.getSource("infra").setData({ type: "FeatureCollection", features: merged });
    setCount("infra", merged.length);
    $("exposure-summary").textContent =
      `${res.features.length} of ${res.sites_checked} sites within ${res.meta.radius_km} km of ` +
      `${res.hazards_checked.toLocaleString()} hazards in the time window.`;
    renderExposure(res.features);
  } catch (err) {
    toast(`Exposure: ${err.message}`, true, 7000);
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze current view";
  }
});
function renderExposure(features) {
  const ol = $("exposure-list");
  ol.innerHTML = "";
  features.slice(0, 50).forEach((f) => {
    const p = f.properties;
    const li = document.createElement("li");
    li.innerHTML = `<div class="title">${esc(p.title)}</div>
      <div>${chips(p.hazard_sources)}</div>
      <div class="meta">Nearest: ${p.nearest_km} km · ${esc(p.nearest_hazard)}</div>`;
    li.addEventListener("click", () => {
      map.flyTo({ center: f.geometry.coordinates, zoom: 11 });
      showPopup({ ...f, layer: { id: "infra" } }, f.geometry.coordinates);
    });
    ol.appendChild(li);
  });
}
