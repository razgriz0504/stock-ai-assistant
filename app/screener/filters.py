"""Stock screener filter implementations.

Each filter function has signature:
    filter_xxx(df: DataFrame, info: dict, params: dict) -> bool

Where:
    df: DataFrame with OHLCV + computed indicators (pandas_ta columns)
    info: dict with fundamental data from yfinance
    params: dict with user-configured parameters for this filter
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Technical Filters
# ═══════════════════════════════════════════════════════════════

def filter_ma_arrangement(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """EMA multi-timeframe arrangement filter.

    Daily: Close > EMA_5 > EMA_10 > EMA_20, all sloping upward
    Weekly: Close > EMA_5w > EMA_10w > EMA_20w, all sloping upward

    params: {"direction": "bullish" | "bearish"}
    """
    if len(df) < 30:
        return False

    direction = params.get("direction", "bullish")

    # ── Daily check ──
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = last["Close"]

    ema5 = last.get("EMA_5")
    ema10 = last.get("EMA_10")
    ema20 = last.get("EMA_20")
    if any(v is None or pd.isna(v) for v in [ema5, ema10, ema20]):
        return False

    # Daily arrangement
    if direction == "bullish":
        if not (close > ema5 > ema10 > ema20):
            return False
    else:
        if not (close < ema5 < ema10 < ema20):
            return False

    # Daily slope: all EMAs rising (compare with previous day)
    prev_ema5 = prev.get("EMA_5")
    prev_ema10 = prev.get("EMA_10")
    prev_ema20 = prev.get("EMA_20")
    if any(v is None or pd.isna(v) for v in [prev_ema5, prev_ema10, prev_ema20]):
        return False

    if direction == "bullish":
        if not (ema5 > prev_ema5 and ema10 > prev_ema10 and ema20 > prev_ema20):
            return False
    else:
        if not (ema5 < prev_ema5 and ema10 < prev_ema10 and ema20 < prev_ema20):
            return False

    # ── Weekly check ──
    try:
        # Ensure DatetimeIndex for resample
        if not isinstance(df.index, pd.DatetimeIndex):
            df_w = df.copy()
            df_w.index = pd.to_datetime(df_w.index)
        else:
            df_w = df

        # Remove timezone info if present (avoids resample issues)
        if df_w.index.tz is not None:
            df_w = df_w.copy()
            df_w.index = df_w.index.tz_localize(None)

        weekly = df_w.resample("W").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum"
        }).dropna()

        if len(weekly) < 22:
            return False

        # Compute weekly EMAs
        weekly["EMA_5w"] = weekly["Close"].ewm(span=5, adjust=False).mean()
        weekly["EMA_10w"] = weekly["Close"].ewm(span=10, adjust=False).mean()
        weekly["EMA_20w"] = weekly["Close"].ewm(span=20, adjust=False).mean()

        wlast = weekly.iloc[-1]
        wprev = weekly.iloc[-2]

        wema5 = wlast.get("EMA_5w")
        wema10 = wlast.get("EMA_10w")
        wema20 = wlast.get("EMA_20w")
        wclose = wlast["Close"]

        if any(v is None or pd.isna(v) for v in [wema5, wema10, wema20, wclose]):
            return False

        # Weekly arrangement
        if direction == "bullish":
            if not (wclose > wema5 > wema10 > wema20):
                return False
        else:
            if not (wclose < wema5 < wema10 < wema20):
                return False

        # Weekly slope
        prev_wema5 = wprev.get("EMA_5w")
        prev_wema10 = wprev.get("EMA_10w")
        prev_wema20 = wprev.get("EMA_20w")
        if any(v is None or pd.isna(v) for v in [prev_wema5, prev_wema10, prev_wema20]):
            return False

        if direction == "bullish":
            if not (wema5 > prev_wema5 and wema10 > prev_wema10 and wema20 > prev_wema20):
                return False
        else:
            if not (wema5 < prev_wema5 and wema10 < prev_wema10 and wema20 < prev_wema20):
                return False

    except Exception as e:
        logger.debug(f"MA weekly check error: {e}")
        return False

    return True


def filter_macd_golden_cross(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """MACD golden cross: MACD line crosses above signal within last N bars.
    params: {"lookback": 3}
    """
    lookback = params.get("lookback", 3)
    macd_col = "MACD_12_26_9"
    signal_col = "MACDs_12_26_9"

    if macd_col not in df.columns or signal_col not in df.columns:
        return False
    if len(df) < lookback + 1:
        return False

    recent = df.iloc[-(lookback + 1):]
    macd = recent[macd_col]
    signal = recent[signal_col]

    if macd.isna().any() or signal.isna().any():
        return False

    # Check if crossover happened in the lookback window
    diff = macd - signal
    for i in range(1, len(diff)):
        if diff.iloc[i] > 0 and diff.iloc[i - 1] <= 0:
            return True
    return False


def filter_kdj_oversold_bounce(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """KDJ oversold bounce: J crosses above 20 from below within last N bars.
    params: {"lookback": 3}
    """
    lookback = params.get("lookback", 3)
    j_col = "J_9_3"

    if j_col not in df.columns:
        return False
    if len(df) < lookback + 1:
        return False

    recent = df[j_col].iloc[-(lookback + 1):]
    if recent.isna().any():
        return False

    for i in range(1, len(recent)):
        if recent.iloc[i] > 20 and recent.iloc[i - 1] <= 20:
            return True
    return False


def filter_volume_breakout(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Volume breakout: today's volume > multiplier * Vol_MA20.
    params: {"multiplier": 2.0}
    """
    multiplier = params.get("multiplier", 2.0)

    if "Vol_SMA_20" not in df.columns or len(df) < 1:
        return False

    last = df.iloc[-1]
    vol = last.get("Volume")
    vol_ma = last.get("Vol_SMA_20")

    if vol is None or vol_ma is None or pd.isna(vol) or pd.isna(vol_ma) or vol_ma == 0:
        return False

    return vol > multiplier * vol_ma


def filter_rsi_zone(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """RSI zone filter: RSI_14 within [min, max].
    params: {"min": 30, "max": 70}
    """
    rsi_col = "RSI_14"
    if rsi_col not in df.columns or len(df) < 1:
        return False

    rsi = df[rsi_col].iloc[-1]
    if pd.isna(rsi):
        return False

    rsi_min = params.get("min", 30)
    rsi_max = params.get("max", 70)
    return rsi_min <= rsi <= rsi_max


def filter_bb_squeeze(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Bollinger Band filter.
    params: {"mode": "squeeze" | "breakout", "width_threshold": 0.15}
    squeeze: BB width < threshold (low volatility, potential breakout)
    breakout: price > upper band
    """
    mode = params.get("mode", "breakout")
    bbu_col = "BBU_20_2.0"
    bbl_col = "BBL_20_2.0"
    bbm_col = "BBM_20_2.0"

    if bbu_col not in df.columns or bbl_col not in df.columns:
        return False
    if len(df) < 1:
        return False

    last = df.iloc[-1]
    upper = last.get(bbu_col)
    lower = last.get(bbl_col)
    middle = last.get(bbm_col)
    close = last["Close"]

    if any(pd.isna(v) for v in [upper, lower, middle] if v is not None):
        return False

    if mode == "breakout":
        return close > upper if upper and not pd.isna(upper) else False
    else:  # squeeze
        threshold = params.get("width_threshold", 0.15)
        if middle and middle > 0 and not pd.isna(middle):
            width = (upper - lower) / middle
            return width < threshold
        return False


def filter_atr_filter(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """ATR volatility filter: ATR as % of price within range.
    params: {"min_pct": 1.0, "max_pct": 5.0}
    """
    atr_col = "ATRr_14"
    if atr_col not in df.columns:
        return False
    if len(df) < 1:
        return False

    last = df.iloc[-1]
    atr = last.get(atr_col)
    close = last["Close"]

    if atr is None or pd.isna(atr) or close == 0:
        return False

    atr_pct = (atr / close) * 100
    min_pct = params.get("min_pct", 0)
    max_pct = params.get("max_pct", 100)
    return min_pct <= atr_pct <= max_pct


def filter_trend_initiation(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Trend initiation filter: detects stocks just starting an uptrend.

    Conditions (all must be met):
    1. EMA_5 crossed above EMA_20 within last N days (was below before)
    2. Volume above 1.5x average (confirms breakout)
    3. MACD histogram turned positive (momentum shift)
    4. Price above EMA_20 (confirmed above key MA)

    params: {"lookback": 5, "vol_multiplier": 1.5}
    """
    lookback = params.get("lookback", 5)
    vol_mult = params.get("vol_multiplier", 1.5)

    if len(df) < lookback + 5:
        return False

    # Check required columns exist
    required = ["EMA_5", "EMA_20", "Volume_Ratio", "MACDh_12_26_9"]
    for col in required:
        if col not in df.columns:
            return False

    last = df.iloc[-1]
    close = last["Close"]
    ema20 = last.get("EMA_20")

    if ema20 is None or pd.isna(ema20):
        return False

    # Condition 4: Price must be above EMA_20
    if close <= ema20:
        return False

    # Condition 1: EMA_5 crossed above EMA_20 within lookback days
    # Check that EMA_5 was below EMA_20 before the crossover
    recent = df.iloc[-(lookback + 2):]
    ema5_series = recent["EMA_5"]
    ema20_series = recent["EMA_20"]

    if ema5_series.isna().any() or ema20_series.isna().any():
        return False

    cross_found = False
    for i in range(1, len(recent)):
        prev_above = ema5_series.iloc[i - 1] > ema20_series.iloc[i - 1]
        curr_above = ema5_series.iloc[i] > ema20_series.iloc[i]
        if not prev_above and curr_above:
            cross_found = True
            break

    if not cross_found:
        return False

    # Condition 2: Volume confirmation - at least one day in lookback has elevated volume
    vol_ratio = df["Volume_Ratio"].iloc[-lookback:]
    if vol_ratio.isna().all():
        return False
    if vol_ratio.max() < vol_mult:
        return False

    # Condition 3: MACD histogram positive (momentum turning up)
    macdh = last.get("MACDh_12_26_9")
    if macdh is None or pd.isna(macdh):
        return False
    if macdh <= 0:
        return False

    return True


# ═══════════════════════════════════════════════════════════════
# Fundamental Filters
# ═══════════════════════════════════════════════════════════════

def filter_pe_range(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """PE ratio within range.
    params: {"min": 5, "max": 30}
    """
    pe = info.get("pe_ratio")
    if pe is None:
        return False
    return params.get("min", 0) <= pe <= params.get("max", 999)


def filter_market_cap(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Market cap filter.
    params: {"tier": "large" | "mid" | "small"} or {"min": 1e10, "max": 1e12}
    large: > 200B, mid: 10B-200B, small: < 10B
    """
    cap = info.get("market_cap")
    if cap is None:
        return False

    tier = params.get("tier")
    if tier:
        if tier == "large":
            return cap >= 200_000_000_000
        elif tier == "mid":
            return 10_000_000_000 <= cap < 200_000_000_000
        elif tier == "small":
            return cap < 10_000_000_000
    else:
        min_cap = params.get("min", 0)
        max_cap = params.get("max", float("inf"))
        return min_cap <= cap <= max_cap

    return False


def filter_revenue_growth(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Revenue growth filter.
    params: {"min_pct": 10}
    Note: info["revenue_growth"] is already in percent (e.g. 15.0 means 15%)
    """
    growth = info.get("revenue_growth")
    if growth is None:
        return False
    return growth >= params.get("min_pct", 0)


def filter_roe(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """ROE filter.
    params: {"min_pct": 15}
    """
    roe = info.get("roe")
    if roe is None:
        return False
    return roe >= params.get("min_pct", 0)


def filter_dividend_yield(df: pd.DataFrame, info: dict, params: dict) -> bool:
    """Dividend yield filter.
    params: {"min_pct": 1.0}
    """
    dy = info.get("dividend_yield")
    if dy is None:
        return False
    return dy >= params.get("min_pct", 0)


# ═══════════════════════════════════════════════════════════════
# Filter Registry
# ═══════════════════════════════════════════════════════════════

TECHNICAL_FILTERS = {
    "ma_arrangement": filter_ma_arrangement,
    "trend_initiation": filter_trend_initiation,
    "macd_golden_cross": filter_macd_golden_cross,
    "kdj_oversold_bounce": filter_kdj_oversold_bounce,
    "volume_breakout": filter_volume_breakout,
    "rsi_zone": filter_rsi_zone,
    "bb_squeeze": filter_bb_squeeze,
    "atr_filter": filter_atr_filter,
}

FUNDAMENTAL_FILTERS = {
    "pe_range": filter_pe_range,
    "market_cap": filter_market_cap,
    "revenue_growth": filter_revenue_growth,
    "roe_filter": filter_roe,
    "dividend_yield": filter_dividend_yield,
}

ALL_FILTERS = {**TECHNICAL_FILTERS, **FUNDAMENTAL_FILTERS}


def apply_fundamental_filters(info: dict, filters_config: dict) -> tuple[bool, dict]:
    """Apply all enabled fundamental filters.

    Returns (passed: bool, details: dict of {filter_name: bool})
    """
    details = {}
    fundamental_config = filters_config.get("fundamental", {})

    for name, func in FUNDAMENTAL_FILTERS.items():
        cfg = fundamental_config.get(name, {})
        if not cfg.get("enabled", False):
            continue
        passed = func(pd.DataFrame(), info, cfg)
        details[name] = passed
        if not passed:
            return False, details

    return True, details


def apply_technical_filters(df: pd.DataFrame, info: dict, filters_config: dict) -> tuple[bool, dict]:
    """Apply all enabled technical filters.

    Returns (passed: bool, details: dict of {filter_name: bool})
    """
    details = {}
    technical_config = filters_config.get("technical", {})

    for name, func in TECHNICAL_FILTERS.items():
        cfg = technical_config.get(name, {})
        if not cfg.get("enabled", False):
            continue
        passed = func(df, info, cfg)
        details[name] = passed
        if not passed:
            return False, details

    return True, details
