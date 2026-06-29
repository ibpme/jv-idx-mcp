#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "ta-lib>=0.6.8",
#   "yfinance>=0.2.0",
#   "numpy>=1.20",
# ]
# ///

"""
Technical Analysis Aggregator — runs a curated set of TA-Lib indicators over
OHLCV data fetched from Yahoo Finance, returning the latest computed value per
indicator grouped by category.

Usage (CLI):
    uv run ta_analysis.py BBCA
    uv run ta_analysis.py BBCA --period 6mo --interval 1d --output str
    uv run ta_analysis.py BBCA --start 2024-01-01 --end 2024-12-31

Usage (module):
    from ta_analysis import compute_ta
    result = compute_ta("BBCA", output="dict")
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import talib

try:
    from .yfinance_ohlcv import fetch_ohlcv
except ImportError:
    from yfinance_ohlcv import fetch_ohlcv  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last(arr) -> float | None:
    """Return the last non-NaN value in a numpy array, or None if all NaN."""
    if arr is None:
        return None
    arr = np.asarray(arr, dtype=float)
    valid = arr[~np.isnan(arr)]
    return float(valid[-1]) if len(valid) > 0 else None


def _r(value) -> float | None:
    """Round to 6 significant figures, return None for NaN/None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return float(f"{value:.6g}")


# ---------------------------------------------------------------------------
# Indicator computation — one function per group
# ---------------------------------------------------------------------------


def _compute_overlap(open_, high, low, close) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for p in [20, 50, 200]:
        out[f"SMA_{p}"] = _r(_last(talib.SMA(close, timeperiod=p)))
    for p in [9, 21, 50, 200]:
        out[f"EMA_{p}"] = _r(_last(talib.EMA(close, timeperiod=p)))

    out["WMA_20"] = _r(_last(talib.WMA(close, timeperiod=20)))
    out["DEMA_21"] = _r(_last(talib.DEMA(close, timeperiod=21)))
    out["TEMA_21"] = _r(_last(talib.TEMA(close, timeperiod=21)))
    out["TRIMA_20"] = _r(_last(talib.TRIMA(close, timeperiod=20)))
    out["KAMA_10"] = _r(_last(talib.KAMA(close, timeperiod=10)))
    out["T3_5"] = _r(_last(talib.T3(close, timeperiod=5, vfactor=0.7)))
    out["HT_TRENDLINE"] = _r(_last(talib.HT_TRENDLINE(close)))

    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
    bb_upper = _last(upper)
    bb_middle = _last(middle)
    bb_lower = _last(lower)
    last_close = float(close[-1]) if len(close) > 0 else None
    if (
        bb_upper is not None
        and bb_lower is not None
        and (bb_upper - bb_lower) != 0
        and last_close is not None
    ):
        pct_b = (last_close - bb_lower) / (bb_upper - bb_lower)
    else:
        pct_b = None
    out["BB_upper"] = _r(bb_upper)
    out["BB_middle"] = _r(bb_middle)
    out["BB_lower"] = _r(bb_lower)
    out["BB_pct_b"] = _r(pct_b)

    out["SAR"] = _r(_last(talib.SAR(high, low, acceleration=0.02, maximum=0.2)))
    out["MIDPOINT_14"] = _r(_last(talib.MIDPOINT(close, timeperiod=14)))
    out["MIDPRICE_14"] = _r(_last(talib.MIDPRICE(high, low, timeperiod=14)))

    return out


def _compute_momentum(open_, high, low, close, volume) -> dict[str, Any]:
    out: dict[str, Any] = {}

    out["RSI_14"] = _r(_last(talib.RSI(close, timeperiod=14)))

    macd, macd_sig, macd_hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    out["MACD"] = _r(_last(macd))
    out["MACD_signal"] = _r(_last(macd_sig))
    out["MACD_hist"] = _r(_last(macd_hist))

    out["ADX_14"] = _r(_last(talib.ADX(high, low, close, timeperiod=14)))
    out["ADXR_14"] = _r(_last(talib.ADXR(high, low, close, timeperiod=14)))
    out["CCI_20"] = _r(_last(talib.CCI(high, low, close, timeperiod=20)))
    out["MFI_14"] = _r(_last(talib.MFI(high, low, close, volume, timeperiod=14)))

    slowk, slowd = talib.STOCH(
        high, low, close, fastk_period=5, slowk_period=3, slowd_period=3
    )
    out["STOCH_slowk"] = _r(_last(slowk))
    out["STOCH_slowd"] = _r(_last(slowd))

    fastk, fastd = talib.STOCHF(high, low, close, fastk_period=5, fastd_period=3)
    out["STOCHF_fastk"] = _r(_last(fastk))
    out["STOCHF_fastd"] = _r(_last(fastd))

    rsi_fastk, rsi_fastd = talib.STOCHRSI(
        close, timeperiod=14, fastk_period=5, fastd_period=3
    )
    out["STOCHRSI_fastk"] = _r(_last(rsi_fastk))
    out["STOCHRSI_fastd"] = _r(_last(rsi_fastd))

    out["WILLR_14"] = _r(_last(talib.WILLR(high, low, close, timeperiod=14)))
    out["MOM_10"] = _r(_last(talib.MOM(close, timeperiod=10)))
    out["ROC_10"] = _r(_last(talib.ROC(close, timeperiod=10)))

    aroon_down, aroon_up = talib.AROON(high, low, timeperiod=14)
    out["AROON_down"] = _r(_last(aroon_down))
    out["AROON_up"] = _r(_last(aroon_up))

    out["AROONOSC_14"] = _r(_last(talib.AROONOSC(high, low, timeperiod=14)))
    out["BOP"] = _r(_last(talib.BOP(open_, high, low, close)))
    out["DX_14"] = _r(_last(talib.DX(high, low, close, timeperiod=14)))
    out["MINUS_DI_14"] = _r(_last(talib.MINUS_DI(high, low, close, timeperiod=14)))
    out["PLUS_DI_14"] = _r(_last(talib.PLUS_DI(high, low, close, timeperiod=14)))
    out["ULTOSC"] = _r(
        _last(
            talib.ULTOSC(
                high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28
            )
        )
    )
    out["CMO_14"] = _r(_last(talib.CMO(close, timeperiod=14)))
    out["APO"] = _r(_last(talib.APO(close, fastperiod=12, slowperiod=26)))
    out["PPO"] = _r(_last(talib.PPO(close, fastperiod=12, slowperiod=26)))
    out["TRIX_15"] = _r(_last(talib.TRIX(close, timeperiod=15)))

    return out


def _compute_volatility(high, low, close) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["ATR_14"] = _r(_last(talib.ATR(high, low, close, timeperiod=14)))
    out["NATR_14"] = _r(_last(talib.NATR(high, low, close, timeperiod=14)))
    out["TRANGE"] = _r(_last(talib.TRANGE(high, low, close)))
    return out


def _compute_volume(high, low, close, volume) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["AD"] = _r(_last(talib.AD(high, low, close, volume)))
    out["ADOSC"] = _r(
        _last(talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10))
    )
    out["OBV"] = _r(_last(talib.OBV(close, volume)))
    return out


def _compute_cycle(close) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["HT_DCPERIOD"] = _r(_last(talib.HT_DCPERIOD(close)))
    out["HT_DCPHASE"] = _r(_last(talib.HT_DCPHASE(close)))

    inphase, quad = talib.HT_PHASOR(close)
    out["HT_PHASOR_inphase"] = _r(_last(inphase))
    out["HT_PHASOR_quad"] = _r(_last(quad))

    sine, leadsine = talib.HT_SINE(close)
    out["HT_SINE"] = _r(_last(sine))
    out["HT_LEADSINE"] = _r(_last(leadsine))

    out["HT_TRENDMODE"] = _r(_last(talib.HT_TRENDMODE(close).astype(float)))

    return out


def _compute_statistics(high, low, close) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["BETA_5"] = _r(_last(talib.BETA(high, low, timeperiod=5)))
    out["CORREL_30"] = _r(_last(talib.CORREL(high, low, timeperiod=30)))
    out["LINEARREG_14"] = _r(_last(talib.LINEARREG(close, timeperiod=14)))
    out["LINEARREG_SLOPE_14"] = _r(_last(talib.LINEARREG_SLOPE(close, timeperiod=14)))
    out["STDDEV_20"] = _r(_last(talib.STDDEV(close, timeperiod=20, nbdev=1)))
    out["TSF_14"] = _r(_last(talib.TSF(close, timeperiod=14)))
    return out


# All 61 TA-Lib CDL pattern functions
_CDL_PATTERNS = [
    "CDL2CROWS",
    "CDL3BLACKCROWS",
    "CDL3INSIDE",
    "CDL3LINESTRIKE",
    "CDL3OUTSIDE",
    "CDL3STARSINSOUTH",
    "CDL3WHITESOLDIERS",
    "CDLABANDONEDBABY",
    "CDLADVANCEBLOCK",
    "CDLBELTHOLD",
    "CDLBREAKAWAY",
    "CDLCLOSINGMARUBOZU",
    "CDLCONCEALBABYSWALL",
    "CDLCOUNTERATTACK",
    "CDLDARKCLOUDCOVER",
    "CDLDOJI",
    "CDLDOJISTAR",
    "CDLDRAGONFLYDOJI",
    "CDLENGULFING",
    "CDLEVENINGDOJISTAR",
    "CDLEVENINGSTAR",
    "CDLGAPSIDESIDEWHITE",
    "CDLGRAVESTONEDOJI",
    "CDLHAMMER",
    "CDLHANGINGMAN",
    "CDLHARAMI",
    "CDLHARAMICROSS",
    "CDLHIGHWAVE",
    "CDLHIKKAKE",
    "CDLHIKKAKEMOD",
    "CDLHOMINGPIGEON",
    "CDLIDENTICAL3CROWS",
    "CDLINNECK",
    "CDLINVERTEDHAMMER",
    "CDLKICKING",
    "CDLKICKINGBYLENGTH",
    "CDLLADDERBOTTOM",
    "CDLLONGLEGGEDDOJI",
    "CDLLONGLINE",
    "CDLMARUBOZU",
    "CDLMATCHINGLOW",
    "CDLMATHOLD",
    "CDLMORNINGDOJISTAR",
    "CDLMORNINGSTAR",
    "CDLONNECK",
    "CDLPIERCING",
    "CDLRICKSHAWMAN",
    "CDLRISEFALL3METHODS",
    "CDLSEPARATINGLINES",
    "CDLSHOOTINGSTAR",
    "CDLSHORTLINE",
    "CDLSPINNINGTOP",
    "CDLSTALLEDPATTERN",
    "CDLSTICKSANDWICH",
    "CDLTAKURI",
    "CDLTASUKIGAP",
    "CDLTHRUSTING",
    "CDLTRISTAR",
    "CDLUNIQUE3RIVER",
    "CDLUPSIDEGAP2CROWS",
    "CDLXSIDEGAP3METHODS",
]


def _compute_patterns(open_, high, low, close) -> dict[str, int]:
    out: dict[str, int] = {}
    for name in _CDL_PATTERNS:
        fn = getattr(talib, name, None)
        if fn is None:
            continue
        try:
            result = fn(open_, high, low, close)
            val = int(_last(result.astype(float)) or 0)
            if val != 0:
                out[name] = val
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_ta(
    code: str,
    period: str | None = "3mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    output: str = "json",  # "json" | "dict" | "str"
) -> dict | str:
    """
    Compute technical analysis indicators for a single IDX stock.

    Args:
        code     : IDX ticker, e.g. "BBCA" (.JK appended automatically)
        period   : Lookback period, e.g. "3mo", "1y" (default: "3mo")
        interval : Bar size, e.g. "1d" (default: "1d")
        start    : Start date "YYYY-MM-DD" (alternative to period)
        end      : End date "YYYY-MM-DD" (alternative to period)
        output   : "json" (default) | "dict" | "str"

    Returns:
        dict if output="dict", str otherwise.
    """
    if output not in ("json", "dict", "str"):
        raise ValueError(f"output must be 'json', 'dict', or 'str', got {output!r}")

    df = fetch_ohlcv(
        code,
        period=period,
        interval=interval,
        start=start,
        end=end,
        output="dataframe",
    )

    open_ = df["Open"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    volume = df["Volume"].to_numpy(dtype=float)

    ticker_sym = (
        code.upper() + ".JK" if not code.upper().endswith(".JK") else code.upper()
    )
    as_of = str(df.index[-1]) if len(df) > 0 else None

    result = {
        "stock": code.upper().replace(".JK", ""),
        "ticker": ticker_sym,
        "as_of": as_of,
        "period": period,
        "interval": interval,
        "bars": len(df),
        "overlap": _compute_overlap(open_, high, low, close),
        "momentum": _compute_momentum(open_, high, low, close, volume),
        "volatility": _compute_volatility(high, low, close),
        "volume": _compute_volume(high, low, close, volume),
        "patterns": _compute_patterns(open_, high, low, close),
        "cycle": _compute_cycle(close),
        "statistics": _compute_statistics(high, low, close),
    }

    if output == "dict":
        return result

    if output == "json":
        return json.dumps(result, default=float)

    # output == "str"
    lines = [
        f"Stock    : {result['stock']} ({result['ticker']})",
        f"As of    : {result['as_of']}  |  Period: {result['period']}  |  Interval: {result['interval']}",
        f"Bars     : {result['bars']}",
        "",
    ]

    group_labels = [
        ("overlap", "Overlap Studies"),
        ("momentum", "Momentum Indicators"),
        ("volatility", "Volatility"),
        ("volume", "Volume"),
        ("cycle", "Cycle Indicators"),
        ("statistics", "Statistic Functions"),
        ("patterns", "Pattern Recognition (active signals only)"),
    ]

    for key, label in group_labels:
        group = result[key]
        lines.append(f"{'─' * 50}")
        lines.append(f"  {label}")
        lines.append(f"{'─' * 50}")
        if not group:
            lines.append("  (no active signals)")
        else:
            col_w = max(len(k) for k in group) + 2
            for k, v in group.items():
                lines.append(f"  {k:<{col_w}}: {v}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Technical analysis indicators for IDX stocks via TA-Lib"
    )
    parser.add_argument("ticker", help="IDX ticker, e.g. BBCA")
    parser.add_argument(
        "--period", default="3mo", help="Lookback period (default: 3mo)"
    )
    parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d)")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--output", default="str", help="Output format: json|str|dict (default: str)"
    )

    args = parser.parse_args()

    # When start/end provided, period should be None
    period = args.period
    if args.start is not None or args.end is not None:
        period = None

    result = compute_ta(
        args.ticker,
        period=period,
        interval=args.interval,
        start=args.start,
        end=args.end,
        output=args.output,
    )

    if isinstance(result, dict):
        print(json.dumps(result, indent=2, default=float))
    else:
        print(result)
