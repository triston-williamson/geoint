"""Settings loaded from environment variables / the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_PLACEHOLDERS = {"", "your_key_here", "changeme"}


def _key(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return None if value in _PLACEHOLDERS else value


FIRMS_MAP_KEY = _key("FIRMS_MAP_KEY")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
USER_AGENT = "geoint-dashboard/0.1 (open-data research tool)"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "40"))
STATIC_DIR = ROOT / "static"
