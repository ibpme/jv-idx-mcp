#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "curl_cffi>=0.7.0",
# ]
# ///
import json
import time
from pathlib import Path
from typing import Optional

from curl_cffi import requests

CACHE_FILE = Path(__file__).parent / "profiles_cache.json"
CACHE_TTL_SECONDS = 86400 * 7  # 7 days

IDX_URL = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfilesDetail"
IDX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.idx.co.id/",
}


def _fetch_profile(code: str) -> Optional[dict]:
    response = requests.get(
        IDX_URL,
        headers=IDX_HEADERS,
        params={"KodeEmiten": code, "language": "id-id"},
        timeout=15,
        impersonate="chrome120",
    )
    response.raise_for_status()
    return response.json()


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    return json.loads(CACHE_FILE.read_text())


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache))


def get_profile(code: str) -> Optional[dict]:
    """Return the company profile for a stock code, loading from cache or fetching fresh data."""
    code = code.upper()
    cache = _load_cache()
    entry = cache.get(code)
    if entry and time.time() - entry.get("fetched_at", 0) <= CACHE_TTL_SECONDS:
        return entry["data"]
    data = _fetch_profile(code)
    if data is None:
        return None
    cache[code] = {"fetched_at": time.time(), "data": data}
    _save_cache(cache)
    return data


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        code = sys.argv[1]
        profile = get_profile(code)
        if profile:
            print(json.dumps(profile))
        else:
            print(f"Profile for '{code}' not found.")
            sys.exit(1)
    else:
        cache = _load_cache()
        print(f"Cached profiles: {len(cache)}")
        if cache:
            sample_code = next(iter(cache))
            print(f"Sample — {sample_code}: {cache[sample_code]['data']}")
