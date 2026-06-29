"""
TA-Lib Natural Language Layer — indicator resolution, abstract API dispatch,
and alias mapping for ~130 stock-relevant indicators.

Provides three core functions:
  - list_indicators(group?, search?) → discovery
  - compute_single_indicator(code, indicator, ...) → dynamic single-indicator
  - (get_ta_summary wraps ta_analysis.compute_ta directly in server.py)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import talib
from talib import abstract

try:
    from .yfinance_ohlcv import fetch_ohlcv
except ImportError:
    from yfinance_ohlcv import fetch_ohlcv  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Groups to exclude — not stock indicators
EXCLUDED_GROUPS = {"Math Transform", "Math Operators"}

# Natural language alias → TA-Lib function name
ALIAS_MAP: dict[str, str] = {
    "bollinger bands": "BBANDS",
    "bollinger": "BBANDS",
    "relative strength": "RSI",
    "relative strength index": "RSI",
    "stochastic": "STOCH",
    "stochastic oscillator": "STOCH",
    "average true range": "ATR",
    "on balance volume": "OBV",
    "parabolic sar": "SAR",
    "parabolic stop and reverse": "SAR",
    "moving average convergence": "MACD",
    "moving average convergence divergence": "MACD",
    "commodity channel": "CCI",
    "commodity channel index": "CCI",
    "simple moving average": "SMA",
    "exponential moving average": "EMA",
    "weighted moving average": "WMA",
    "double exponential moving average": "DEMA",
    "triple exponential moving average": "TEMA",
    "kaufman adaptive moving average": "KAMA",
    "average directional index": "ADX",
    "money flow index": "MFI",
    "williams %r": "WILLR",
    "williams percent r": "WILLR",
    "rate of change": "ROC",
    "momentum": "MOM",
    "aroon oscillator": "AROONOSC",
    "chande momentum oscillator": "CMO",
    "ultimate oscillator": "ULTOSC",
    "accumulation distribution": "AD",
    "chaikin oscillator": "ADOSC",
    "chaikin ad oscillator": "ADOSC",
    "hilbert transform": "HT_TRENDLINE",
    "linear regression": "LINEARREG",
    "standard deviation": "STDDEV",
    "true range": "TRANGE",
    "normalized atr": "NATR",
    "balance of power": "BOP",
    "directional index": "DX",
    "minus directional indicator": "MINUS_DI",
    "plus directional indicator": "PLUS_DI",
    "percentage price oscillator": "PPO",
    "absolute price oscillator": "APO",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_stock_groups() -> dict[str, list[str]]:
    """Return TA-Lib function groups, excluding non-stock groups."""
    all_groups = talib.get_function_groups()
    return {
        group: funcs
        for group, funcs in all_groups.items()
        if group not in EXCLUDED_GROUPS
    }


def _get_indicator_info(name: str) -> dict[str, Any]:
    """Get metadata for a single indicator via TA-Lib abstract API."""
    fn = abstract.Function(name)
    info = fn.info

    params = {}
    for pname, pval in info.get("parameters", {}).items():
        params[pname] = pval

    output_names = list(info.get("output_names", []))

    return {
        "name": info["name"],
        "display_name": info["display_name"],
        "group": info["group"],
        "parameters": params,
        "output_names": output_names,
    }


def _resolve_indicator(indicator: str) -> str:
    """Resolve a natural language indicator name or alias to a TA-Lib function name."""
    # Try direct uppercase match first
    upper = indicator.strip().upper()
    all_funcs = set()
    for funcs in talib.get_function_groups().values():
        all_funcs.update(funcs)

    if upper in all_funcs:
        return upper

    # Try alias map (case-insensitive)
    lower = indicator.strip().lower()
    if lower in ALIAS_MAP:
        return ALIAS_MAP[lower]

    # Try partial match on alias keys
    for alias, func_name in ALIAS_MAP.items():
        if lower in alias or alias in lower:
            return func_name

    raise ValueError(
        f"Unknown indicator: {indicator!r}. "
        f"Use list_indicators(search={indicator!r}) to find available indicators."
    )


def _r(value) -> float | None:
    """Round to 6 significant figures, return None for NaN/None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return float(f"{value:.6g}")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def list_indicators(
    group: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """
    List available TA-Lib indicators with metadata.

    Args:
        group:  Filter by group name (partial, case-insensitive match).
        search: Search keyword matching name, display_name, or aliases.

    Returns:
        List of indicator info dicts.
    """
    stock_groups = _get_stock_groups()
    results: list[dict[str, Any]] = []

    for grp, funcs in stock_groups.items():
        # Filter by group if specified
        if group and group.lower() not in grp.lower():
            continue

        for func_name in funcs:
            try:
                info = _get_indicator_info(func_name)
            except Exception:
                continue

            # Filter by search keyword if specified
            if search:
                search_lower = search.lower()
                searchable = (
                    info["name"].lower()
                    + " "
                    + info["display_name"].lower()
                    + " "
                    + " ".join(
                        alias
                        for alias, target in ALIAS_MAP.items()
                        if target == func_name
                    )
                )
                if search_lower not in searchable:
                    continue

            results.append(info)

    return results


def compute_single_indicator(
    code: str,
    indicator: str,
    params: dict[str, Any] | None = None,
    period: str | None = "3mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    series: bool = False,
    last_n: int | None = None,
) -> dict[str, Any]:
    """
    Compute a single TA-Lib indicator dynamically via the abstract API.

    Args:
        code:      IDX stock ticker, e.g. "BBCA"
        indicator: Indicator name or natural language alias, e.g. "RSI", "bollinger bands"
        params:    Parameter overrides, e.g. {"timeperiod": 7}
        period:    Lookback period, e.g. "3mo", "6mo", "1y"
        interval:  Bar size, e.g. "1d"
        start:     Start date "YYYY-MM-DD" (alternative to period)
        end:       End date "YYYY-MM-DD" (alternative to period)
        series:    If True, return time series; if False (default), return latest value only
        last_n:    When series=True, limit to last N data points

    Returns:
        Dict with stock info, indicator metadata, parameters used, and computed data.
    """
    # 1. Resolve indicator name
    func_name = _resolve_indicator(indicator)

    # 2. Get indicator metadata
    info = _get_indicator_info(func_name)

    # 3. Validate params
    valid_params = info["parameters"]
    if params:
        invalid = set(params.keys()) - set(valid_params.keys())
        if invalid:
            raise ValueError(
                f"Invalid parameter(s) for {func_name}: {invalid}. "
                f"Valid parameters: {valid_params}"
            )

    # 4. Fetch OHLCV data
    if start is not None or end is not None:
        period = None

    df = fetch_ohlcv(
        code,
        period=period,
        interval=interval,
        start=start,
        end=end,
        output="dataframe",
    )

    # 5. Build inputs dict
    inputs = {
        "open": df["Open"].to_numpy(dtype=float),
        "high": df["High"].to_numpy(dtype=float),
        "low": df["Low"].to_numpy(dtype=float),
        "close": df["Close"].to_numpy(dtype=float),
        "volume": df["Volume"].to_numpy(dtype=float),
    }

    # 6. Run indicator via abstract API
    fn = abstract.Function(func_name)
    if params:
        fn.set_parameters(params)
    result_arrays = fn.run(inputs)

    # Get actual parameters used (including defaults)
    parameters_used = dict(fn.get_parameters())

    # 7. Format output
    output_names = info["output_names"]

    # Handle single vs multi output
    if not isinstance(result_arrays, list):
        result_arrays = [result_arrays]

    # Ensure output_names matches result_arrays length
    if len(output_names) != len(result_arrays):
        output_names = [f"output_{i}" for i in range(len(result_arrays))]

    ticker_sym = (
        code.upper() + ".JK" if not code.upper().endswith(".JK") else code.upper()
    )
    dates = [str(d) for d in df.index]

    if series:
        # Return time series
        data: dict[str, Any] = {}
        for oname, arr in zip(output_names, result_arrays):
            arr = np.asarray(arr, dtype=float)
            values = [_r(float(v)) if not np.isnan(v) else None for v in arr]
            paired = list(zip(dates, values))
            # Filter out leading NaN values
            first_valid = next(
                (i for i, (_, v) in enumerate(paired) if v is not None), len(paired)
            )
            paired = paired[first_valid:]
            if last_n is not None and last_n > 0:
                paired = paired[-last_n:]
            data[oname] = [{"date": d, "value": v} for d, v in paired]
    else:
        # Return latest value only
        data = {}
        for oname, arr in zip(output_names, result_arrays):
            arr = np.asarray(arr, dtype=float)
            valid = arr[~np.isnan(arr)]
            if len(valid) == 0:
                raise ValueError(
                    f"All values are NaN for {func_name} on {code.upper()}. "
                    f"Try a longer period (e.g. period='6mo' or period='1y') "
                    f"to provide enough data for this indicator."
                )
            data[oname] = _r(float(valid[-1]))

    as_of = str(df.index[-1]) if len(df) > 0 else None

    return {
        "stock": code.upper().replace(".JK", ""),
        "ticker": ticker_sym,
        "as_of": as_of,
        "indicator": func_name,
        "display_name": info["display_name"],
        "group": info["group"],
        "parameters_used": parameters_used,
        "bars": len(df),
        "data": data,
    }
