# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "beautifulsoup4",
# ]
# ///

"""
Fetches and parses broker summary data from IndoPremier for any IDX stock ticker.

Usage (as a module)::

    from ipot_broker_summary import fetch_broker_summary

    data = fetch_broker_summary("DOOH", start="2026-03-01", end="2026-03-02")
    data = fetch_broker_summary("DOOH", start="2026-03-01", end="2026-03-02",
                                fd="F", board="RG")

Returns a dict::

    {
        "stock": "DOOH",
        "period": {"start": "03/01/2026", "end": "03/02/2026"},
        "filters": {"fd": "all", "board": "all"},
        "summary": {
            "total_value_raw": "11.5 B",
            "foreign_net_value_raw": "1.8 B",
            "total_lot": 750449,
            "avg_price": 154,
        },
        "buyers": [
            {"rank": 1, "broker": "AK", "type": "foreign",
             "lot": 132572, "value_raw": "2.0 B", "avg": 154},
            # type is one of: "foreign", "local", "bumn", "retail", "unknown"
            # Brokers XL, XC, PD, YP are always typed as "retail"
            ...
        ],
        "sellers": [...],
        "net_positions": [
            {"broker": "AK", "type": "foreign",
             "net_lot": 89017, "buy_lot": 132572, "sell_lot": 43555},
            ...
        ],
    }
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.indopremier.com/module/saham/include/data-brokersummary.php"

# Span class → broker ownership type
_BROKER_TYPE_MAP = {
    "text-foreign": "foreign",
    "text-local": "local",
    "text-bumn": "bumn",
}

# Brokers that should always be classified as retail regardless of HTML type
_RETAIL_BROKERS = {"XL", "XC", "PD", "YP"}

# Valid param values
_FD_VALUES = {"all", "F", "D"}
_BOARD_VALUES = {"all", "RG", "TN", "NG"}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _to_ipot_date(date_str: str) -> str:
    """
    Convert a date string to IndoPremier's MM/DD/YYYY format.

    Accepts:
        - ISO format:  "2026-03-01"  → "03/01/2026"
        - Already MM/DD/YYYY: "03/01/2026"  → returned as-is
    """
    if re.match(r"\d{2}/\d{2}/\d{4}", date_str):
        return date_str
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%Y")
    except ValueError:
        raise ValueError(
            f"date must be ISO 'YYYY-MM-DD' or 'MM/DD/YYYY', got {date_str!r}"
        )


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------


def _parse_lot(raw: str) -> int | None:
    """'132,572 ' → 132572"""
    cleaned = raw.strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _parse_avg(raw: str) -> float | None:
    """'154 ' → 154.0"""
    cleaned = raw.strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_summary_lot(raw: str) -> int | None:
    """'750,449 ' → 750449"""
    return _parse_lot(raw)


def _parse_summary_avg(raw: str) -> float | None:
    return _parse_avg(raw)


def _broker_type_from_span(span, broker: str = "") -> str:
    """Extract broker ownership type from a <span> element's class list."""
    if broker.upper() in _RETAIL_BROKERS:
        return "retail"
    if span is None:
        return "unknown"
    classes = span.get("class", [])
    for cls in classes:
        if cls in _BROKER_TYPE_MAP:
            return _BROKER_TYPE_MAP[cls]
    return "unknown"


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def _parse_summary_footer(tfoot) -> dict:
    """Parse the tfoot row: 'T. Val : 11.5 B  F. NVal : 1.8 B  T.Lot : 750,449  Avg : 154'"""
    text = tfoot.get_text(" ", strip=True)

    summary: dict = {}

    m = re.search(r"T\.\s*Val\s*:\s*([\d.,]+\s*[BM]?)", text)
    summary["total_value_raw"] = m.group(1).strip() if m else None

    m = re.search(r"F\.\s*NVal\s*:\s*([\d.,]+\s*[BM]?)", text)
    summary["foreign_net_value_raw"] = m.group(1).strip() if m else None

    m = re.search(r"T\.Lot\s*:\s*([\d,]+)", text)
    summary["total_lot"] = _parse_summary_lot(m.group(1)) if m else None

    m = re.search(r"Avg\s*:\s*([\d,]+)", text)
    summary["avg_price"] = _parse_summary_avg(m.group(1)) if m else None

    return summary


def _parse_table(soup: BeautifulSoup) -> tuple[list[dict], list[dict], dict]:
    """
    Parse the broker summary table.

    Returns:
        buyers        : list of buyer dicts, ordered by rank
        sellers       : list of seller dicts, ordered by rank
        summary       : footer summary dict
    """
    table = soup.find("table", class_="table-summary")
    if table is None:
        raise ValueError("Broker summary table not found in response.")

    buyers: list[dict] = []
    sellers: list[dict] = []

    tbody = table.find("tbody")
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) != 9:
            continue

        # --- Buyer side (cells 0-3) ---
        b_span = cells[0].find("span")
        b_broker = (
            b_span.get_text(strip=True) if b_span else cells[0].get_text(strip=True)
        )
        buyer = {
            "rank": None,  # filled below
            "broker": b_broker,
            "type": _broker_type_from_span(b_span, b_broker),
            "lot": _parse_lot(cells[1].get_text()),
            "value_raw": cells[2].get_text(strip=True),
            "avg": _parse_avg(cells[3].get_text()),
        }

        # --- Rank (cell 4) ---
        rank_text = cells[4].get_text(strip=True)
        rank = int(rank_text) if rank_text.isdigit() else None
        buyer["rank"] = rank

        # --- Seller side (cells 5-8) ---
        s_span = cells[5].find("span")
        s_broker = (
            s_span.get_text(strip=True) if s_span else cells[5].get_text(strip=True)
        )
        seller = {
            "rank": rank,
            "broker": s_broker,
            "type": _broker_type_from_span(s_span, s_broker),
            "lot": _parse_lot(cells[6].get_text()),
            "value_raw": cells[7].get_text(strip=True),
            "avg": _parse_avg(cells[8].get_text()),
        }

        buyers.append(buyer)
        sellers.append(seller)

    tfoot = table.find("tfoot")
    summary = _parse_summary_footer(tfoot) if tfoot else {}

    return buyers, sellers, summary


def _compute_net_positions(buyers: list[dict], sellers: list[dict]) -> list[dict]:
    """
    Merge buyer and seller lists into net positions per broker.
    Sorted by net_lot descending (largest accumulators first).
    """
    positions: dict[str, dict] = {}

    for b in buyers:
        broker = b["broker"]
        if broker not in positions:
            positions[broker] = {
                "broker": broker,
                "type": b["type"],
                "buy_lot": 0,
                "sell_lot": 0,
                "buy_avg": None,
                "sell_avg": None,
            }
        positions[broker]["buy_lot"] += b["lot"] or 0
        positions[broker]["buy_avg"] = b["avg"]

    for s in sellers:
        broker = s["broker"]
        if broker not in positions:
            positions[broker] = {
                "broker": broker,
                "type": s["type"],
                "buy_lot": 0,
                "sell_lot": 0,
                "buy_avg": None,
                "sell_avg": None,
            }
        positions[broker]["sell_lot"] += s["lot"] or 0
        positions[broker]["sell_avg"] = s["avg"]

    result = []
    for pos in positions.values():
        net = pos["buy_lot"] - pos["sell_lot"]
        result.append(
            {
                "broker": pos["broker"],
                "type": pos["type"],
                "net_lot": net,
                "buy_lot": pos["buy_lot"],
                "sell_lot": pos["sell_lot"],
                "buy_avg": pos["buy_avg"],
                "sell_avg": pos["sell_avg"],
            }
        )

    result.sort(key=lambda x: x["net_lot"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_broker_summary(
    code: str,
    start: str,
    end: str,
    fd: str = "all",
    board: str = "all",
) -> dict:
    """
    Fetch and parse broker summary data for an IDX stock from IndoPremier.

    Args:
        code   : IDX stock ticker, e.g. "BBCA", "TLKM", "DOOH"
        start  : Start date — ISO "YYYY-MM-DD" or "MM/DD/YYYY"
        end    : End date   — ISO "YYYY-MM-DD" or "MM/DD/YYYY"
        fd     : Foreign/Domestic filter — "all" | "F" | "D"  (default "all")
        board  : Board filter — "all" | "RG" | "TN" | "NG"    (default "all")

    Returns:
        dict with keys: stock, period, filters, summary, buyers, sellers,
        net_positions.

    Raises:
        ValueError  : invalid parameter values or table not found in response
        httpx.HTTPError : network / HTTP errors
    """
    if fd not in _FD_VALUES:
        raise ValueError(f"fd must be one of {_FD_VALUES}, got {fd!r}")
    if board not in _BOARD_VALUES:
        raise ValueError(f"board must be one of {_BOARD_VALUES}, got {board!r}")

    start_fmt = _to_ipot_date(start)
    end_fmt = _to_ipot_date(end)

    params = {
        "code": code.upper(),
        "start": start_fmt,
        "end": end_fmt,
        "fd": fd,
        "board": board,
    }

    response = httpx.get(BASE_URL, params=params, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    buyers, sellers, summary = _parse_table(soup)
    net_positions = _compute_net_positions(buyers, sellers)

    return {
        "stock": code.upper(),
        "period": {"start": start_fmt, "end": end_fmt},
        "filters": {"fd": fd, "board": board},
        "summary": summary,
        "buyers": buyers,
        "sellers": sellers,
        "net_positions": net_positions,
    }


# ---------------------------------------------------------------------------
# Broker Flow
# ---------------------------------------------------------------------------


def fetch_broker_flow(
    code: str,
    lookback_days: int = 365,
    interval_days: int = 30,
    end: str | None = None,
    fd: str = "all",
    board: str = "all",
) -> dict:
    """
    Fetch broker flow: track each broker's activity across non-overlapping
    time intervals over a rolling window.

    Args:
        code           : IDX stock ticker, e.g. "BBCA", "DOOH"
        lookback_days  : Total window size in days (default 365 = 1 year)
        interval_days  : Size of each interval in days (default 30 = ~1 month)
        end            : Window end date — ISO "YYYY-MM-DD" (default: today)
        fd             : Foreign/Domestic filter — "all" | "F" | "D"
        board          : Board filter — "all" | "RG" | "TN" | "NG"

    Returns:
        dict with keys:
            stock         : ticker
            window        : {start, end} of full range (ISO strings)
            lookback_days : as provided
            interval_days : as provided
            filters       : {fd, board}
            periods       : list of "YYYY-MM-DD/YYYY-MM-DD" strings, one per interval
            broker_flow   : {
                "<BROKER>": {
                    "type": "foreign" | "local" | "bumn" | "unknown",
                    "total_net_lot": int,
                    "flow": [
                        {
                            "period": "YYYY-MM-DD/YYYY-MM-DD",
                            "net_lot": int,
                            "buy_lot": int,
                            "sell_lot": int,
                            "buy_avg": float | null,
                            "sell_avg": float | null,
                        },
                        ...  (one entry per interval, 0/null when broker absent)
                    ]
                },
                ...
            }
    """
    if fd not in _FD_VALUES:
        raise ValueError(f"fd must be one of {_FD_VALUES}, got {fd!r}")
    if board not in _BOARD_VALUES:
        raise ValueError(f"board must be one of {_BOARD_VALUES}, got {board!r}")

    end_dt = (
        datetime.strptime(end, "%Y-%m-%d")
        if end
        else datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    )
    start_dt = end_dt - timedelta(days=lookback_days)

    # Build list of (interval_start, interval_end) datetime pairs
    intervals: list[tuple[datetime, datetime]] = []
    cursor = start_dt
    while cursor < end_dt:
        interval_end = min(cursor + timedelta(days=interval_days - 1), end_dt)
        intervals.append((cursor, interval_end))
        cursor += timedelta(days=interval_days)

    periods = [
        f"{s.strftime('%Y-%m-%d')}/{e.strftime('%Y-%m-%d')}" for s, e in intervals
    ]

    # Fetch each interval and collect per-broker data
    # broker_data[broker] = list of slot dicts (one per interval, None if absent)
    broker_data: dict[str, dict] = {}  # broker -> {type, flow: list}

    for idx, (iv_start, iv_end) in enumerate(intervals):
        try:
            result = fetch_broker_summary(
                code,
                start=iv_start.strftime("%Y-%m-%d"),
                end=iv_end.strftime("%Y-%m-%d"),
                fd=fd,
                board=board,
            )
            net_positions = result["net_positions"]
        except Exception:
            net_positions = []

        # Index this interval's data by broker
        interval_by_broker: dict[str, dict] = {p["broker"]: p for p in net_positions}

        # Register any new brokers seen in this interval
        for broker, pos in interval_by_broker.items():
            if broker not in broker_data:
                broker_data[broker] = {
                    "type": pos["type"],
                    "flow": [None] * len(intervals),
                }

        # Fill in this interval's slot for every known broker
        for broker, data in broker_data.items():
            pos = interval_by_broker.get(broker)
            if pos:
                data["flow"][idx] = {
                    "period": periods[idx],
                    "net_lot": pos["net_lot"],
                    "buy_lot": pos["buy_lot"],
                    "sell_lot": pos["sell_lot"],
                    "buy_avg": pos["buy_avg"],
                    "sell_avg": pos["sell_avg"],
                }
            else:
                data["flow"][idx] = {
                    "period": periods[idx],
                    "net_lot": 0,
                    "buy_lot": 0,
                    "sell_lot": 0,
                    "buy_avg": None,
                    "sell_avg": None,
                }

    # Compute total_net_lot per broker and build final output
    # Replace any None slots (broker not yet seen) with zeroed entries
    broker_flow: dict[str, dict] = {}
    for broker, data in broker_data.items():
        flow = [
            (
                slot
                if slot is not None
                else {
                    "period": periods[i],
                    "net_lot": 0,
                    "buy_lot": 0,
                    "sell_lot": 0,
                    "buy_avg": None,
                    "sell_avg": None,
                }
            )
            for i, slot in enumerate(data["flow"])
        ]
        total = sum(slot["net_lot"] for slot in flow)
        broker_flow[broker] = {
            "type": data["type"],
            "total_net_lot": total,
            "flow": flow,
        }

    # Sort brokers by abs(total_net_lot) descending — most active first
    broker_flow = dict(
        sorted(
            broker_flow.items(),
            key=lambda kv: abs(kv[1]["total_net_lot"]),
            reverse=True,
        )
    )

    return {
        "stock": code.upper(),
        "window": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": end_dt.strftime("%Y-%m-%d"),
        },
        "lookback_days": lookback_days,
        "interval_days": interval_days,
        "filters": {"fd": fd, "board": board},
        "periods": periods,
        "broker_flow": broker_flow,
    }


# ---------------------------------------------------------------------------
# Cumulative Broker Flow
# ---------------------------------------------------------------------------


def fetch_broker_flow_cumulative(
    code: str,
    lookback_days: int = 365,
    interval_days: int = 30,
    end: str | None = None,
    fd: str = "all",
    board: str = "all",
) -> dict:
    """
    Fetch cumulative broker flow: each snapshot covers [window_start → snapshot_end],
    expanding by interval_days each step.

    This reveals how each broker's total accumulated position grows (or shrinks)
    over time, along with the delta between consecutive snapshots.

    Args:
        code           : IDX stock ticker, e.g. "BBCA", "DOOH"
        lookback_days  : Total window size in days (default 365 = 1 year)
        interval_days  : Step size in days (default 30 = ~1 month)
        end            : Window end date — ISO "YYYY-MM-DD" (default: today)
        fd             : Foreign/Domestic filter — "all" | "F" | "D"
        board          : Board filter — "all" | "RG" | "TN" | "NG"

    Returns:
        dict with keys:
            stock         : ticker
            window        : {start, end} of full range (ISO strings)
            lookback_days : as provided
            interval_days : as provided
            filters       : {fd, board}
            snapshots     : list of "YYYY-MM-DD/YYYY-MM-DD" strings (start→each step end)
            broker_flow   : {
                "<BROKER>": {
                    "type": "foreign" | "local" | "bumn" | "unknown",
                    "final_net_lot": int,   # net lot at the last snapshot
                    "flow": [
                        {
                            "snapshot": "YYYY-MM-DD/YYYY-MM-DD",
                            "cumulative_net_lot": int,
                            "period_delta": int,      # vs. previous snapshot (0 for first)
                            "cumulative_buy_lot": int,
                            "cumulative_sell_lot": int,
                            "buy_avg": float | null,  # avg for full window up to this point
                            "sell_avg": float | null,
                        },
                        ...
                    ]
                },
                ...
            }

    Note — top-10 visibility constraint:
        The source API returns only the top-10 buyers and top-10 sellers for any
        given window. As the cumulative window expands, a broker that dominated a
        short slice may no longer rank in the top-10 over the longer period, so
        its cumulative_net_lot will show 0 even though real activity occurred.
        Use fetch_broker_flow (non-overlapping) alongside this function for a
        more complete picture: non-overlapping slices capture brokers active in
        each sub-period even if they drop off longer-window rankings.
    """
    if fd not in _FD_VALUES:
        raise ValueError(f"fd must be one of {_FD_VALUES}, got {fd!r}")
    if board not in _BOARD_VALUES:
        raise ValueError(f"board must be one of {_BOARD_VALUES}, got {board!r}")

    end_dt = (
        datetime.strptime(end, "%Y-%m-%d")
        if end
        else datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    )
    start_dt = end_dt - timedelta(days=lookback_days)

    # Build snapshot endpoints: start_dt fixed, end moves forward by interval_days
    snapshot_ends: list[datetime] = []
    cursor = start_dt + timedelta(days=interval_days - 1)
    while cursor < end_dt:
        snapshot_ends.append(cursor)
        cursor += timedelta(days=interval_days)
    # Always include the final end_dt as the last snapshot
    if not snapshot_ends or snapshot_ends[-1] < end_dt:
        snapshot_ends.append(end_dt)

    snapshots = [
        f"{start_dt.strftime('%Y-%m-%d')}/{e.strftime('%Y-%m-%d')}"
        for e in snapshot_ends
    ]

    # broker_data[broker] = {type, flow: list of slot dicts | None}
    broker_data: dict[str, dict] = {}

    for idx, snap_end in enumerate(snapshot_ends):
        try:
            result = fetch_broker_summary(
                code,
                start=start_dt.strftime("%Y-%m-%d"),
                end=snap_end.strftime("%Y-%m-%d"),
                fd=fd,
                board=board,
            )
            net_positions = result["net_positions"]
        except Exception:
            net_positions = []

        by_broker: dict[str, dict] = {p["broker"]: p for p in net_positions}

        # Register any new brokers
        for broker, pos in by_broker.items():
            if broker not in broker_data:
                broker_data[broker] = {
                    "type": pos["type"],
                    "flow": [None] * len(snapshot_ends),
                }

        # Fill slot for every known broker
        for broker, data in broker_data.items():
            pos = by_broker.get(broker)
            if pos:
                data["flow"][idx] = {
                    "snapshot": snapshots[idx],
                    "cumulative_net_lot": pos["net_lot"],
                    "cumulative_buy_lot": pos["buy_lot"],
                    "cumulative_sell_lot": pos["sell_lot"],
                    "buy_avg": pos["buy_avg"],
                    "sell_avg": pos["sell_avg"],
                }
            else:
                data["flow"][idx] = {
                    "snapshot": snapshots[idx],
                    "cumulative_net_lot": 0,
                    "cumulative_buy_lot": 0,
                    "cumulative_sell_lot": 0,
                    "buy_avg": None,
                    "sell_avg": None,
                }

    # Build final output: replace None slots and compute period_delta
    broker_flow: dict[str, dict] = {}
    for broker, data in broker_data.items():
        flow: list[dict] = []
        prev_net = 0
        for i, slot in enumerate(data["flow"]):
            if slot is None:
                slot = {
                    "snapshot": snapshots[i],
                    "cumulative_net_lot": 0,
                    "cumulative_buy_lot": 0,
                    "cumulative_sell_lot": 0,
                    "buy_avg": None,
                    "sell_avg": None,
                }
            delta = slot["cumulative_net_lot"] - prev_net
            prev_net = slot["cumulative_net_lot"]
            flow.append({**slot, "period_delta": delta})

        final_net = flow[-1]["cumulative_net_lot"] if flow else 0
        broker_flow[broker] = {
            "type": data["type"],
            "final_net_lot": final_net,
            "flow": flow,
        }

    # Sort by abs(final_net_lot) descending
    broker_flow = dict(
        sorted(
            broker_flow.items(),
            key=lambda kv: abs(kv[1]["final_net_lot"]),
            reverse=True,
        )
    )

    return {
        "stock": code.upper(),
        "window": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": end_dt.strftime("%Y-%m-%d"),
        },
        "lookback_days": lookback_days,
        "interval_days": interval_days,
        "filters": {"fd": fd, "board": board},
        "snapshots": snapshots,
        "broker_flow": broker_flow,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Usage:
    #   uv run ipot_broker_summary.py DOOH 2026-03-01 2026-03-02 [fd] [board]
    #   uv run ipot_broker_summary.py flow DOOH [lookback_days] [interval_days] [fd] [board]
    #   uv run ipot_broker_summary.py cumflow DOOH [lookback_days] [interval_days] [fd] [board]

    if len(sys.argv) > 1 and sys.argv[1] == "cumflow":
        code = sys.argv[2] if len(sys.argv) > 2 else "DOOH"
        lookback = int(sys.argv[3]) if len(sys.argv) > 3 else 365
        interval = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        fd = sys.argv[5] if len(sys.argv) > 5 else "all"
        board = sys.argv[6] if len(sys.argv) > 6 else "all"
        result = fetch_broker_flow_cumulative(
            code, lookback_days=lookback, interval_days=interval, fd=fd, board=board
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "flow":
        code = sys.argv[2] if len(sys.argv) > 2 else "DOOH"
        lookback = int(sys.argv[3]) if len(sys.argv) > 3 else 365
        interval = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        fd = sys.argv[5] if len(sys.argv) > 5 else "all"
        board = sys.argv[6] if len(sys.argv) > 6 else "all"
        result = fetch_broker_flow(
            code, lookback_days=lookback, interval_days=interval, fd=fd, board=board
        )
    else:
        code = sys.argv[1] if len(sys.argv) > 1 else "DOOH"
        start = sys.argv[2] if len(sys.argv) > 2 else "2026-03-01"
        end = sys.argv[3] if len(sys.argv) > 3 else "2026-03-02"
        fd = sys.argv[4] if len(sys.argv) > 4 else "all"
        board = sys.argv[5] if len(sys.argv) > 5 else "all"
        result = fetch_broker_summary(code, start=start, end=end, fd=fd, board=board)

    print(json.dumps(result, indent=2))
