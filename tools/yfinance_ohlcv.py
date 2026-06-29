#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "yfinance>=0.2.0",
# ]
# ///

"""
Fetches OHLCV (Open, High, Low, Close, Volume) data from Yahoo Finance for IDX stock tickers.

Indonesian stocks on Yahoo Finance use the `.JK` suffix (e.g. BBCA → BBCA.JK).
The suffix is appended automatically if not already present.

Usage (as a module):
    from yfinance_ohlcv import fetch_ohlcv

    # Single ticker — 1-month daily bars
    df = fetch_ohlcv("BBCA")

    # Date range instead of period
    df = fetch_ohlcv("BBCA", start="2024-01-01", end="2024-06-30")

    # Multi-ticker batch fetch — returns dict[str, DataFrame]
    dfs = fetch_ohlcv(["BBCA", "TLKM", "GOTO"], period="3mo", interval="1d")

    # Intraday with WIB timezone (default tz="Asia/Jakarta")
    df = fetch_ohlcv("BBCA", period="5d", interval="1h")

    # Other output formats
    data = fetch_ohlcv("BBCA", output="dict")   # list of row dicts (single) or dict of lists (multi)
    s    = fetch_ohlcv("BBCA", output="json")   # JSON string
    s    = fetch_ohlcv("BBCA", output="csv")    # CSV string
    s    = fetch_ohlcv("BBCA", output="str")    # human-readable table

    # Disable NaN row dropping
    df = fetch_ohlcv("BBCA", dropna=False)

Valid periods  : 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
Valid intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
  Note: intraday intervals (< 1d) are only available for the last 60 days.
"""

from __future__ import annotations

import json

import yfinance as yf

OutputFormat = str  # Literal["dataframe", "dict", "json", "csv", "str"]

VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
VALID_INTERVALS = {
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "1d",
    "5d",
    "1wk",
    "1mo",
    "3mo",
}
DAILY_INTERVALS = {"1d", "5d", "1wk", "1mo", "3mo"}

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _yahoo_ticker(code: str) -> str:
    """Return the Yahoo Finance ticker symbol for an IDX stock code."""
    code = code.upper().strip()
    if not code.endswith(".JK"):
        code += ".JK"
    return code


def _post_process(df, interval: str, tz: str, dropna: bool):
    """Normalize index (date-only for daily+, WIB for intraday) and drop NaN rows."""
    if interval in DAILY_INTERVALS:
        df.index = df.index.date
    else:
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(tz)

    if dropna:
        df = df.dropna()

    return df


def _format_index(df, interval: str):
    """Convert index to strings suitable for serialization."""
    if interval in DAILY_INTERVALS:
        return df.index.astype(str)
    else:
        return df.index.strftime("%Y-%m-%d %H:%M")


def fetch_ohlcv(
    code: str | list[str],
    period: str | None = "1mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    tz: str = "Asia/Jakarta",
    dropna: bool = True,
    output: OutputFormat = "dataframe",
):
    """
    Fetch OHLCV data for one or more IDX stocks from Yahoo Finance.

    Args:
        code     : IDX ticker or list of tickers, e.g. "BBCA" or ["BBCA", "TLKM"]
                   (`.JK` appended automatically)
        period   : Lookback window — "1d" | "5d" | "1mo" | "3mo" | "6mo" |
                   "1y" | "2y" | "5y" | "10y" | "ytd" | "max"  (default: "1mo")
                   Set to None when using start/end.
        interval : Bar size — "1m" | "2m" | "5m" | "15m" | "30m" | "60m" | "90m" |
                   "1h" | "1d" | "5d" | "1wk" | "1mo" | "3mo"  (default: "1d")
        start    : Start date string "YYYY-MM-DD" (alternative to period)
        end      : End date string "YYYY-MM-DD" (alternative to period)
        tz       : Timezone for intraday bars (default: "Asia/Jakarta" / WIB)
        dropna   : Drop rows where any OHLCV value is NaN (default: True)
        output   : Return format —
                   "dataframe" → pandas DataFrame / dict[str, DataFrame] for multi
                   "dict"      → list of row dicts / dict[str, list[dict]] for multi
                   "json"      → JSON string
                   "csv"       → CSV string
                   "str"       → human-readable plain-text table

    Returns:
        Single ticker: DataFrame, list[dict], or str depending on output.
        Multi-ticker: dict[str, DataFrame], dict[str, list[dict]], or str depending on output.

    Raises:
        ValueError  : if conflicting or invalid parameters are provided.
        RuntimeError: if no data is returned (ticker may be delisted or wrong code).
    """
    # Validate period/start/end
    if start is not None or end is not None:
        if period is not None and period != "1mo":
            raise ValueError("Cannot specify both period and start/end date range")
        period = None  # use start/end path
    elif period is None:
        period = "1mo"

    if period is not None and period not in VALID_PERIODS:
        raise ValueError(
            f"period must be one of {sorted(VALID_PERIODS)}, got {period!r}"
        )
    if interval not in VALID_INTERVALS:
        raise ValueError(
            f"interval must be one of {sorted(VALID_INTERVALS)}, got {interval!r}"
        )
    if output not in ("dataframe", "dict", "json", "csv", "str"):
        raise ValueError(
            f"output must be 'dataframe', 'dict', 'json', 'csv', or 'str', got {output!r}"
        )

    multi = isinstance(code, list)

    if multi:
        return _fetch_multi(code, period, interval, start, end, tz, dropna, output)
    else:
        return _fetch_single(code, period, interval, start, end, tz, dropna, output)


def _fetch_single(code, period, interval, start, end, tz, dropna, output):
    ticker_symbol = _yahoo_ticker(code)
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(
        period=period, interval=interval, start=start, end=end, auto_adjust=True
    )

    if df.empty:
        raise RuntimeError(
            f"No data returned for {ticker_symbol!r}. "
            "Check that the ticker is valid and listed on IDX."
        )

    ohlcv_cols = [c for c in OHLCV_COLS if c in df.columns]
    df = df[ohlcv_cols].copy()
    df = _post_process(df, interval, tz, dropna)

    if output == "dataframe":
        return df

    df_out = df.copy()
    df_out.index = _format_index(df_out, interval)

    if output == "dict":
        return [
            {"Date": date, **{col: row[col] for col in ohlcv_cols}}
            for date, row in df_out.iterrows()
        ]

    if output == "json":
        rows = [
            {"Date": date, **{col: row[col] for col in ohlcv_cols}}
            for date, row in df_out.iterrows()
        ]
        return json.dumps(
            {
                "stock": code.upper(),
                "ticker": _yahoo_ticker(code),
                "period": period,
                "interval": interval,
                "rows": rows,
            },
            default=float,
        )

    if output == "csv":
        return df_out.to_csv()

    # output == "str"
    ticker_symbol = _yahoo_ticker(code)
    range_str = f"{start} to {end}" if (start or end) else period
    header = (
        f"Stock   : {code.upper()} ({ticker_symbol})\n"
        f"Range   : {range_str}  |  Interval: {interval}\n"
        f"Rows    : {len(df_out)}\n"
    )
    return header + "\n" + df_out.to_string()


def _fetch_multi(codes, period, interval, start, end, tz, dropna, output):
    tickers = [_yahoo_ticker(c) for c in codes]
    raw = yf.download(
        tickers,
        period=period,
        interval=interval,
        start=start,
        end=end,
        auto_adjust=True,
        group_by="ticker",
        progress=False,
    )

    results = {}
    for c, sym in zip(codes, tickers):
        key = c.upper()
        if sym in raw.columns.get_level_values(0):
            df = raw[sym].copy()
        else:
            df = (
                raw.copy()
            )  # single-ticker fallback (yf.download flattens for 1 ticker)

        ohlcv_cols = [col for col in OHLCV_COLS if col in df.columns]
        df = df[ohlcv_cols].copy()
        df = _post_process(df, interval, tz, dropna)
        results[key] = df

    if output == "dataframe":
        return results

    if output == "dict":
        out = {}
        for key, df in results.items():
            df_out = df.copy()
            ohlcv_cols = [col for col in OHLCV_COLS if col in df_out.columns]
            df_out.index = _format_index(df_out, interval)
            out[key] = [
                {"Date": date, **{col: row[col] for col in ohlcv_cols}}
                for date, row in df_out.iterrows()
            ]
        return out

    if output == "json":
        out = {}
        for key, df in results.items():
            df_out = df.copy()
            ohlcv_cols = [col for col in OHLCV_COLS if col in df_out.columns]
            df_out.index = _format_index(df_out, interval)
            out[key] = [
                {"Date": date, **{col: row[col] for col in ohlcv_cols}}
                for date, row in df_out.iterrows()
            ]
        return json.dumps(
            {"interval": interval, "tickers": out},
            default=float,
        )

    if output == "csv":
        import io

        parts = []
        for key, df in results.items():
            df_out = df.copy()
            df_out.index = _format_index(df_out, interval)
            df_out.insert(0, "Ticker", key)
            buf = io.StringIO()
            df_out.to_csv(buf)
            parts.append(buf.getvalue())
        return "\n".join(parts)

    # output == "str"
    range_str = f"{start} to {end}" if (start or end) else period
    sections = []
    for key, df in results.items():
        df_out = df.copy()
        df_out.index = _format_index(df_out, interval)
        header = (
            f"Stock   : {key} ({_yahoo_ticker(key)})\n"
            f"Range   : {range_str}  |  Interval: {interval}\n"
            f"Rows    : {len(df_out)}\n"
        )
        sections.append(header + "\n" + df_out.to_string())
    return "\n\n" + ("-" * 60 + "\n").join(sections)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch OHLCV data from Yahoo Finance for IDX stocks"
    )
    parser.add_argument(
        "ticker", help="Ticker or comma-separated tickers, e.g. BBCA or BBCA,TLKM"
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Lookback period, e.g. 1mo, 3mo, 1y (default: 1mo)",
    )
    parser.add_argument(
        "--interval", default="1d", help="Bar interval, e.g. 1d, 1h, 5m (default: 1d)"
    )
    parser.add_argument(
        "--start", default=None, help="Start date YYYY-MM-DD (alternative to --period)"
    )
    parser.add_argument(
        "--end", default=None, help="End date YYYY-MM-DD (alternative to --period)"
    )
    parser.add_argument(
        "--output",
        default="str",
        help="Output format: dataframe|dict|json|csv|str (default: str)",
    )
    parser.add_argument(
        "--tz",
        default="Asia/Jakarta",
        help="Timezone for intraday bars (default: Asia/Jakarta)",
    )
    parser.add_argument(
        "--no-dropna", action="store_true", help="Keep rows with NaN values"
    )

    # Support legacy positional args: ticker period interval output
    args, unknown = parser.parse_known_args()

    # If period not set via flag, check for legacy positional-style unknown args
    if unknown:
        if args.period is None and len(unknown) >= 1:
            args.period = unknown[0]
        if len(unknown) >= 2:
            args.interval = unknown[1]
        if len(unknown) >= 3:
            args.output = unknown[2]

    if args.period is None and args.start is None:
        args.period = "1mo"

    tickers = [t.strip() for t in args.ticker.split(",")]
    code = tickers if len(tickers) > 1 else tickers[0]

    result = fetch_ohlcv(
        code,
        period=args.period,
        interval=args.interval,
        start=args.start,
        end=args.end,
        tz=args.tz,
        dropna=not args.no_dropna,
        output=args.output,
    )

    if hasattr(result, "to_string"):
        print(result.to_string())
    elif isinstance(result, dict) and all(
        hasattr(v, "to_string") for v in result.values()
    ):
        for k, df in result.items():
            print(f"\n{'=' * 40}\n{k}\n{'=' * 40}")
            print(df.to_string())
    else:
        print(result)
