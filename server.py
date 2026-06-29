"""MCP server exposing IDX stock market data as tools."""

from __future__ import annotations

import json
import secrets

import httpx
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from mcp.server.fastmcp import FastMCP
from starlette.responses import Response


class BearerAuthMiddleware:
    """ASGI middleware that enforces Bearer token auth when MCP_API_KEY is set."""

    def __init__(self, app, api_key: str) -> None:
        self.app = app
        self.expected = f"Bearer {api_key}"

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            if not secrets.compare_digest(auth, self.expected):
                await Response("Unauthorized", status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)

from tools.idx_broker_search import lookup_broker_details, lookup_broker_name
from tools.idx_profile import get_profile
from tools.ipot_fundamental import _to_csv, _to_str, fetch_fundamental
from tools.ipot_broker_summary import (
    fetch_broker_summary,
    fetch_broker_flow,
    fetch_broker_flow_cumulative,
)
from tools.ta_analysis import compute_ta
from tools.ta_indicators import list_indicators as _list_indicators
from tools.ta_indicators import compute_single_indicator

import os
mcp = FastMCP("jv-idx-mcp", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))


@mcp.tool()
def get_stock_fundamental(
    code: str,
    quarter: int | None = None,
    output: str = "str",
) -> str:
    """
    Fetch fundamental financial data for an IDX (Indonesia Stock Exchange) stock from IndoPremier.

    Args:
        code: IDX stock ticker, e.g. "BBCA", "TLKM", "GOTO"
        quarter: Reporting period slice:
                   None → Annual / Auto (default)
                   1    → 3-month  (Q1 YTD)
                   2    → 6-month  (H1 YTD)
                   3    → 9-month  (Q1-Q3 YTD)
                   4    → 12-month (full year, same as None)
                   5    → Every quarter side-by-side
        output: Return format:
                   "str"  → Plain-text human-readable summary (default)
                   "json" → JSON-formatted string
                   "csv"  → CSV table (section, metric, period columns)

    Returns:
        Formatted string with balance sheet, income statement, and ratio data.
    """
    if output not in ("str", "json", "csv"):
        output = "str"

    ticker = code.strip().upper()

    try:
        result = fetch_fundamental(ticker, quarter=quarter, output="dict")
    except ValueError as e:
        raise ValueError(f"Invalid request for '{ticker}': {e}") from e
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"HTTP {e.response.status_code} error fetching data for '{ticker}'."
        ) from e
    except httpx.RequestError as e:
        raise ValueError(f"Network error fetching data for '{ticker}': {e}") from e

    assert isinstance(result, dict)
    data: dict = result

    all_empty = all(not metrics for metrics in data["sections"].values())
    if all_empty:
        raise ValueError(
            f"No fundamental data found for '{ticker}'. "
            "Check that it is a valid IDX stock code."
        )

    if output == "json":
        return json.dumps(data)
    if output == "csv":
        return _to_csv(data)
    return _to_str(data)


@mcp.tool()
def get_company_profile(code: str) -> str:
    """
    Fetch the IDX company profile for a listed stock.

    Args:
        code: IDX stock ticker, e.g. "BBCA", "TLKM", "GOTO"

    Returns:
        JSON-formatted string with company profile data from idx.co.id,
        or an error message if the ticker is not found.
    """
    ticker = code.strip().upper()
    try:
        data = get_profile(ticker)
    except CurlHTTPError as e:
        raise ValueError(f"HTTP error fetching profile for '{ticker}': {e}") from e
    except CurlRequestException as e:
        raise ValueError(f"Network error fetching profile for '{ticker}': {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response for '{ticker}': {e}") from e
    except OSError as e:
        raise ValueError(f"Cache file error for '{ticker}': {e}") from e

    if data is None:
        raise ValueError(
            f"No profile found for '{ticker}'. Check that it is a valid IDX stock code."
        )
    return json.dumps(data)


@mcp.tool()
def get_broker_name(codes: list[str]) -> str:
    """
    Look up firm names for one or more IDX broker codes.

    Args:
        codes: List of IDX broker codes, e.g. ["AK", "BK", "YP"]

    Returns:
        JSON-formatted mapping of broker code -> firm name.
        Unknown codes map to null.
    """
    normalized = [c.strip().upper() for c in codes]
    try:
        result = lookup_broker_name(normalized)
    except CurlHTTPError as e:
        raise ValueError(f"HTTP error fetching broker data: {e}") from e
    except CurlRequestException as e:
        raise ValueError(f"Network error fetching broker data: {e}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(
            f"Unexpected response format from broker summary API: {e}"
        ) from e
    except OSError as e:
        raise ValueError(f"Cache file error for broker data: {e}") from e

    missing = [c for c, v in result.items() if v is None]
    if missing:
        raise ValueError(f"Broker code(s) not found: {', '.join(missing)}")
    return json.dumps(result)


@mcp.tool()
def get_broker_details(codes: list[str]) -> str:
    """
    Fetch full trading summary details for one or more IDX brokers.

    Args:
        codes: List of IDX broker codes, e.g. ["AK", "BK", "YP"]

    Returns:
        JSON-formatted mapping of broker code -> details (IDFirm, FirmName,
        Volume, Value, Frequency, Date, etc.).
        Unknown codes map to null.
    """
    normalized = [c.strip().upper() for c in codes]
    try:
        result = lookup_broker_details(normalized)
    except CurlHTTPError as e:
        raise ValueError(f"HTTP error fetching broker data: {e}") from e
    except CurlRequestException as e:
        raise ValueError(f"Network error fetching broker data: {e}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(
            f"Unexpected response format from broker summary API: {e}"
        ) from e
    except OSError as e:
        raise ValueError(f"Cache file error for broker data: {e}") from e

    missing = [c for c, v in result.items() if v is None]
    if missing:
        raise ValueError(f"Broker code(s) not found: {', '.join(missing)}")
    return json.dumps(result)


@mcp.tool()
def get_broker_summary(
    code: str,
    start: str,
    end: str,
    fd: str = "all",
    board: str = "all",
) -> str:
    """
    Fetch broker trading summary for an IDX stock over a date range.

    Shows the top buyers and sellers by lot volume, their average prices,
    broker ownership type (foreign/local/bumn/retail), and net positions per broker.
    Brokers XL, XC, PD, and YP are always classified as retail.

    Args:
        code:  IDX stock ticker, e.g. "BBCA", "TLKM", "DOOH"
        start: Start date in ISO format "YYYY-MM-DD"
        end:   End date in ISO format "YYYY-MM-DD"
        fd:    Foreign/Domestic filter — "all" (default) | "F" (foreign only) | "D" (domestic only)
        board: Board filter — "all" (default) | "RG" (regular) | "TN" (tunai) | "NG" (nego)

    Returns:
        JSON string with keys: stock, period, filters, summary, buyers, sellers, net_positions.
        - summary: total_value_raw, foreign_net_value_raw, total_lot, avg_price
        - buyers/sellers: rank, broker, type (foreign/local/bumn/retail), lot, value_raw, avg
        - net_positions: broker, type (foreign/local/bumn/retail), net_lot, buy_lot, sell_lot, buy_avg, sell_avg
          sorted by net_lot descending (top accumulators first, distributors last)
    """
    ticker = code.strip().upper()
    try:
        result = fetch_broker_summary(ticker, start=start, end=end, fd=fd, board=board)
    except ValueError as e:
        raise ValueError(f"Invalid request for '{ticker}': {e}") from e
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"HTTP {e.response.status_code} error fetching broker summary for '{ticker}'."
        ) from e
    except httpx.RequestError as e:
        raise ValueError(
            f"Network error fetching broker summary for '{ticker}': {e}"
        ) from e

    return json.dumps(result)


@mcp.tool()
def get_broker_flow(
    code: str,
    lookback_days: int = 365,
    interval_days: int = 30,
    end: str | None = None,
    fd: str = "all",
    board: str = "all",
) -> str:
    """
    Fetch non-overlapping broker flow for an IDX stock over a rolling window.

    Divides the window into equal non-overlapping intervals and shows each broker's
    activity (net_lot, buy/sell lots, avg prices) within each independent slice.
    Useful for spotting which brokers were active in specific sub-periods.

    Args:
        code:          IDX stock ticker, e.g. "BBCA", "TLKM", "DOOH"
        lookback_days: Total window size in days (default 365 = 1 year)
        interval_days: Size of each non-overlapping slice in days (default 30 = ~1 month)
        end:           Window end date in ISO format "YYYY-MM-DD" (default: today)
        fd:            Foreign/Domestic filter — "all" | "F" | "D"
        board:         Board filter — "all" | "RG" | "TN" | "NG"

    Returns:
        JSON string with keys: stock, window, lookback_days, interval_days, filters,
        periods, broker_flow.
        - periods: list of "YYYY-MM-DD/YYYY-MM-DD" slice labels
        - broker_flow: per-broker dict with type (foreign/local/bumn/retail), total_net_lot,
          and a flow list. Brokers XL, XC, PD, YP are always typed as retail.
          Each flow entry has: period, net_lot, buy_lot, sell_lot, buy_avg, sell_avg.
          Sorted by abs(total_net_lot) descending.
    """
    ticker = code.strip().upper()
    try:
        result = fetch_broker_flow(
            ticker,
            lookback_days=lookback_days,
            interval_days=interval_days,
            end=end,
            fd=fd,
            board=board,
        )
    except ValueError as e:
        raise ValueError(f"Invalid request for '{ticker}': {e}") from e
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"HTTP {e.response.status_code} error fetching broker flow for '{ticker}'."
        ) from e
    except httpx.RequestError as e:
        raise ValueError(
            f"Network error fetching broker flow for '{ticker}': {e}"
        ) from e

    return json.dumps(result)


@mcp.tool()
def get_broker_flow_cumulative(
    code: str,
    lookback_days: int = 365,
    interval_days: int = 30,
    end: str | None = None,
    fd: str = "all",
    board: str = "all",
) -> str:
    """
    Fetch cumulative broker flow for an IDX stock over a rolling window.

    Each snapshot covers [window_start → snapshot_end], expanding by interval_days
    each step. Shows how each broker's total accumulated position and average prices
    evolve over time, along with the delta vs. the previous snapshot.

    Best used alongside get_broker_flow: non-overlapping slices capture sub-period
    activity, cumulative snapshots reveal who dominated the full window.

    Note: The source API returns only top-10 buyers and sellers per query. A broker
    active in a short slice may drop out of the top-10 over a longer cumulative window,
    so its cumulative_net_lot may show 0 even though real activity occurred in that period.

    Args:
        code:          IDX stock ticker, e.g. "BBCA", "TLKM", "DOOH"
        lookback_days: Total window size in days (default 365 = 1 year)
        interval_days: Step size between snapshots in days (default 30 = ~1 month)
        end:           Window end date in ISO format "YYYY-MM-DD" (default: today)
        fd:            Foreign/Domestic filter — "all" | "F" | "D"
        board:         Board filter — "all" | "RG" | "TN" | "NG"

    Returns:
        JSON string with keys: stock, window, lookback_days, interval_days, filters,
        snapshots, broker_flow.
        - snapshots: list of "YYYY-MM-DD/YYYY-MM-DD" expanding window labels
        - broker_flow: per-broker dict with type (foreign/local/bumn/retail), final_net_lot,
          and a flow list. Brokers XL, XC, PD, YP are always typed as retail.
          Each flow entry has: snapshot, cumulative_net_lot, period_delta,
          cumulative_buy_lot, cumulative_sell_lot, buy_avg, sell_avg.
          Sorted by abs(final_net_lot) descending.
    """
    ticker = code.strip().upper()
    try:
        result = fetch_broker_flow_cumulative(
            ticker,
            lookback_days=lookback_days,
            interval_days=interval_days,
            end=end,
            fd=fd,
            board=board,
        )
    except ValueError as e:
        raise ValueError(f"Invalid request for '{ticker}': {e}") from e
    except httpx.HTTPStatusError as e:
        raise ValueError(
            f"HTTP {e.response.status_code} error fetching cumulative broker flow for '{ticker}'."
        ) from e
    except httpx.RequestError as e:
        raise ValueError(
            f"Network error fetching cumulative broker flow for '{ticker}': {e}"
        ) from e

    return json.dumps(result)


@mcp.tool()
def list_indicators(
    group: str | None = None,
    search: str | None = None,
) -> str:
    """
    List available TA-Lib technical analysis indicators with their parameters.

    Use this tool first to discover indicator names and parameters before calling
    compute_indicator. Covers ~130 stock-relevant indicators across 8 groups:
    Overlap Studies, Momentum, Volatility, Volume, Price Transform, Cycle,
    Pattern Recognition, and Statistics.

    Args:
        group:  Filter by group name (partial, case-insensitive match),
                e.g. "momentum", "overlap", "volume", "pattern"
        search: Search keyword matching indicator name, display name, or aliases,
                e.g. "bollinger", "rsi", "macd", "stochastic"

    Returns:
        JSON string with list of indicators, each containing: name, display_name,
        group, parameters (with defaults), and output_names.
    """
    results = _list_indicators(group=group, search=search)
    if not results:
        msg = "No indicators found"
        if group:
            msg += f" in group matching {group!r}"
        if search:
            msg += f" matching search {search!r}"
        msg += ". Try a broader search or omit filters to see all indicators."
        raise ValueError(msg)
    return json.dumps(results)


@mcp.tool()
def compute_indicator(
    code: str,
    indicator: str,
    params: dict | None = None,
    period: str | None = "3mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    series: bool = False,
    last_n: int | None = None,
) -> str:
    """
    Compute a single technical analysis indicator for an IDX stock.

    Supports ~130 TA-Lib indicators. Accepts natural language names like
    "bollinger bands", "relative strength", "moving average convergence",
    as well as standard codes like "RSI", "BBANDS", "MACD".

    Use list_indicators() first to discover available indicators and their parameters.

    Args:
        code:      IDX stock ticker, e.g. "BBCA", "TLKM", "GOTO"
        indicator: Indicator name or alias, e.g. "RSI", "bollinger bands", "MACD",
                   "stochastic", "average true range", "EMA"
        params:    Optional parameter overrides as a dict, e.g. {"timeperiod": 7}
                   for RSI(7), or {"fastperiod": 10, "slowperiod": 20} for MACD.
                   Omit to use standard defaults.
        period:    Lookback period — "1mo" | "3mo" | "6mo" | "1y" | "2y" | "5y"
                   (default: "3mo"). Set to None when using start/end.
        interval:  Bar size — "1d" | "1wk" | "1mo" (default: "1d")
        start:     Start date "YYYY-MM-DD" (alternative to period)
        end:       End date "YYYY-MM-DD" (alternative to period)
        series:    If True, return time series data; if False (default), return
                   latest value only — more concise for screening.
        last_n:    When series=True, limit output to last N data points to avoid
                   huge responses. E.g. last_n=10 for the most recent 10 bars.

    Returns:
        JSON string with: stock, ticker, as_of, indicator, display_name, group,
        parameters_used, bars, and data (latest values or time series).
    """
    ticker = code.strip().upper()
    try:
        result = compute_single_indicator(
            ticker,
            indicator=indicator,
            params=params,
            period=period,
            interval=interval,
            start=start,
            end=end,
            series=series,
            last_n=last_n,
        )
    except RuntimeError as e:
        raise ValueError(
            f"No data returned for '{ticker}'. "
            "Check that it is a valid IDX stock code."
        ) from e

    return json.dumps(result)


@mcp.tool()
def get_ta_summary(
    code: str,
    period: str | None = "3mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    output: str = "json",
) -> str:
    """
    Get a comprehensive technical analysis summary for an IDX stock.

    Returns ~50 curated indicators' latest values grouped by category:
    overlap studies (SMA, EMA, BBANDS, SAR), momentum (RSI, MACD, STOCH, ADX),
    volatility (ATR), volume (OBV, AD), cycle, statistics, and active candlestick
    pattern signals. Provides a quick "full picture" overview.

    Use compute_indicator() for drill-down into specific indicators or time series.

    Args:
        code:     IDX stock ticker, e.g. "BBCA", "TLKM", "GOTO"
        period:   Lookback period — "1mo" | "3mo" | "6mo" | "1y" | "2y" | "5y"
                  (default: "3mo"). Set to None when using start/end.
        interval: Bar size — "1d" | "1wk" | "1mo" (default: "1d")
        start:    Start date "YYYY-MM-DD" (alternative to period)
        end:      End date "YYYY-MM-DD" (alternative to period)
        output:   Return format — "json" (default) | "str" (human-readable table)

    Returns:
        Formatted string with all indicator values grouped by category.
    """
    if output not in ("json", "str"):
        output = "json"

    ticker = code.strip().upper()

    if start is not None or end is not None:
        period = None

    try:
        result = compute_ta(
            ticker,
            period=period,
            interval=interval,
            start=start,
            end=end,
            output=output,
        )
    except RuntimeError as e:
        raise ValueError(
            f"No data returned for '{ticker}'. "
            "Check that it is a valid IDX stock code."
        ) from e

    if isinstance(result, dict):
        return json.dumps(result, default=float)
    return result


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    api_key = os.getenv("MCP_API_KEY", "")

    if api_key:
        app = mcp.streamable_http_app()
        uvicorn.run(BearerAuthMiddleware(app, api_key), host=host, port=port)
    else:
        mcp.run(transport="streamable-http")
