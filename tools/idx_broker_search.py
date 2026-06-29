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

CACHE_FILE = Path(__file__).parent.parent / ".cache" / "broker_cache.json"
CACHE_TTL_SECONDS = 86400  # 1 day

IDX_URL = "https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary"
IDX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.idx.co.id/",
}


def _fetch_broker() -> list[dict]:
    response = requests.get(
        IDX_URL,
        headers=IDX_HEADERS,
        params={"start": 0, "length": 500},
        timeout=15,
        impersonate="chrome120",
    )
    response.raise_for_status()
    return response.json()["data"]


def _load_cache() -> Optional[dict]:
    if not CACHE_FILE.exists():
        return None
    raw = json.loads(CACHE_FILE.read_text())
    if time.time() - raw.get("fetched_at", 0) > CACHE_TTL_SECONDS:
        return None
    return raw["brokers"]


def _build_and_save_cache() -> dict:
    data = _fetch_broker()
    brokers = {entry["IDFirm"]: entry for entry in data}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"fetched_at": time.time(), "brokers": brokers}))
    return brokers


def get_brokers() -> dict:
    """Return the broker lookup dict, loading from cache or fetching fresh data."""
    cached = _load_cache()
    if cached is not None:
        return cached
    return _build_and_save_cache()


def lookup_broker_name(codes: list[str]) -> dict[str, Optional[str]]:
    """Return a mapping of broker code -> firm name for each code in the list.

    Unknown codes map to None.
    """
    brokers = get_brokers()
    return {
        code: (brokers[code.upper()]["FirmName"] if code.upper() in brokers else None)
        for code in codes
    }


def lookup_broker_details(codes: list[str]) -> dict[str, Optional[dict]]:
    """Return a mapping of broker code -> full broker record for each code in the list.

    Unknown codes map to None. Fields: IDFirm, FirmName, Volume, Value, Frequency, Date, etc.
    """
    brokers = get_brokers()
    return {code: brokers.get(code.upper()) for code in codes}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        codes = sys.argv[1:]
        results = lookup_broker_details(codes)
        missing = [c for c, v in results.items() if v is None]
        found = {c: v for c, v in results.items() if v is not None}
        if found:
            print(json.dumps(found, indent=2))
        if missing:
            print(f"Broker code(s) not found: {', '.join(missing)}")
            sys.exit(1)
    else:
        brokers = get_brokers()
        print(f"Loaded {len(brokers)} brokers.")
        sample_code = next(iter(brokers))
        print(f"Sample — {sample_code}: {brokers[sample_code]['FirmName']}")
