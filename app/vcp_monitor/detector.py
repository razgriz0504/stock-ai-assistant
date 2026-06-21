"""VCP (Volatility Contraction Pattern) Detection Algorithm.

Implements Mark Minervini's VCP pattern recognition using:
- Asymmetric dual-window swing point extraction
- Contraction sequence validation with diminishing depth
- Volume dry-up quantification
- Quality scoring (0-100)

Usage:
    from app.vcp_monitor.detector import detect_vcp
    result = detect_vcp(df, rs_percentile=85.0)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Contraction:
    """A single contraction within a VCP base."""
    name: str               # "T1", "T2", etc.
    start_date: str         # ISO date string
    end_date: str           # ISO date string
    high: float             # Swing high price
    low: float              # Swing low price
    depth_pct: float        # (high - low) / high * 100
    avg_volume: float       # Average volume during this contraction


@dataclass
class VcpResult:
    """Result of VCP detection for a single stock."""
    status: str             # "forming" / "breakout" / "failed"
    score: int              # 0-100 quality score
    pivot_price: float      # The breakout pivot point
    base_start_date: str    # When the base started
    contractions: list[Contraction] = field(default_factory=list)
    volume_dry_ratio: float = 0.0   # Last contraction vol / base avg vol


def detect_vcp(df: pd.DataFrame, rs_percentile: float = 50.0) -> Optional[VcpResult]:
    """Detect VCP pattern in a stock's OHLCV DataFrame.

    Args:
        df: DataFrame with columns [Open, High, Low, Close, Volume], DatetimeIndex
        rs_percentile: The stock's RS rating (0-100) for scoring

    Returns:
        VcpResult if a valid VCP pattern is detected, None otherwise.
    """
    if df.empty or len(df) < 60:
        return None

    try:
        # Ensure we work with a clean copy
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Step 1: Find the base start (significant swing high using large window)
        base_high_idx = _find_base_high(df)
        if base_high_idx is None:
            return None

        # The base is from base_high_idx to end of data
        base_df = df.iloc[base_high_idx:]
        if len(base_df) < 15:  # Need minimum base length
            return None

        # Step 2: Extract contractions using small window within the base
        contractions = _extract_contractions(base_df)
        if not contractions:
            return None

        # Step 3: Validate contraction sequence
        if not _validate_contractions(contractions):
            return None

        # Step 4: Determine pivot and status
        pivot_price = contractions[-1].high
        base_start_date = str(base_df.index[0].date())

        # Calculate volume dry ratio
        base_avg_vol = float(base_df["Volume"].mean())
        last_contraction_vol = contractions[-1].avg_volume
        volume_dry_ratio = last_contraction_vol / base_avg_vol if base_avg_vol > 0 else 1.0

        # Determine status
        last_close = float(df.iloc[-1]["Close"])
        last_volume = float(df.iloc[-1]["Volume"])
        vol_sma20 = float(df["Volume"].iloc[-20:].mean()) if len(df) >= 20 else float(df["Volume"].mean())

        if last_close > pivot_price and last_volume > 1.5 * vol_sma20:
            status = "breakout"
        elif last_close < contractions[-1].low:
            status = "failed"
        else:
            status = "forming"

        # Step 5: Calculate quality score
        score = _calculate_score(contractions, volume_dry_ratio, rs_percentile, base_df)

        return VcpResult(
            status=status,
            score=score,
            pivot_price=round(pivot_price, 2),
            base_start_date=base_start_date,
            contractions=contractions,
            volume_dry_ratio=round(volume_dry_ratio, 3),
        )

    except Exception as e:
        logger.debug(f"VCP detection error: {e}")
        return None


def _find_base_high(df: pd.DataFrame) -> Optional[int]:
    """Find the base starting point (significant swing high) using large window.

    Uses a window of ±15-20 bars to identify the most significant recent peak
    that precedes a consolidation phase.
    """
    window = 15
    highs = df["High"].values
    n = len(highs)

    if n < window * 2 + 30:
        return None

    # Look for swing highs in the last 80% of data (skip very recent for forming patterns)
    # but not in the last 10 bars
    search_start = max(window, int(n * 0.2))
    search_end = n - 10

    swing_highs = []
    for i in range(search_start, search_end):
        left_start = max(0, i - window)
        right_end = min(n, i + window + 1)
        if highs[i] == highs[left_start:right_end].max():
            swing_highs.append(i)

    if not swing_highs:
        return None

    # Pick the most recent significant swing high
    # "Significant" = highest point in recent history that is followed by a decline
    best_idx = None
    best_score = -1

    for idx in reversed(swing_highs[-5:]):  # Check last 5 candidates
        high_val = highs[idx]
        # Check that price declined after this point
        subsequent = df["Close"].iloc[idx:].values
        if len(subsequent) < 10:
            continue
        min_after = subsequent[5:].min()  # Min after 5 bars
        decline_pct = (high_val - min_after) / high_val * 100

        if decline_pct >= 8:  # At least 8% decline to form a base
            # Score by decline magnitude and recency
            recency_score = idx / n  # More recent = higher score
            score = decline_pct * 0.5 + recency_score * 50
            if score > best_score:
                best_score = score
                best_idx = idx

    return best_idx


def _extract_contractions(base_df: pd.DataFrame) -> list[Contraction]:
    """Extract contraction sequence from the base using small window swing detection."""
    small_window = 4
    highs = base_df["High"].values
    lows = base_df["Low"].values
    volumes = base_df["Volume"].values
    dates = base_df.index
    n = len(base_df)

    if n < 15:
        return []

    # Find swing highs and lows with small window
    swing_high_indices = []
    swing_low_indices = []

    for i in range(small_window, n - small_window):
        left_s = max(0, i - small_window)
        right_e = min(n, i + small_window + 1)

        if highs[i] == highs[left_s:right_e].max():
            swing_high_indices.append(i)
        if lows[i] == lows[left_s:right_e].min():
            swing_low_indices.append(i)

    if len(swing_high_indices) < 2 or len(swing_low_indices) < 1:
        return []

    # Build contractions: pair each swing high with the following swing low
    contractions = []
    used_lows = set()

    for i, sh_idx in enumerate(swing_high_indices):
        # Find the next swing low after this swing high
        best_low_idx = None
        for sl_idx in swing_low_indices:
            if sl_idx > sh_idx and sl_idx not in used_lows:
                best_low_idx = sl_idx
                break

        if best_low_idx is None:
            continue

        # Determine end of this contraction (next swing high or end of data)
        end_idx = n - 1
        if i + 1 < len(swing_high_indices):
            end_idx = swing_high_indices[i + 1] - 1

        high_val = float(highs[sh_idx])
        low_val = float(lows[best_low_idx])

        if high_val <= 0:
            continue

        depth_pct = (high_val - low_val) / high_val * 100
        start_date = str(dates[sh_idx].date())
        end_date = str(dates[min(end_idx, n - 1)].date())

        # Average volume in this contraction range
        vol_slice = volumes[sh_idx:min(end_idx + 1, n)]
        avg_vol = float(vol_slice.mean()) if len(vol_slice) > 0 else 0

        contractions.append(Contraction(
            name=f"T{len(contractions) + 1}",
            start_date=start_date,
            end_date=end_date,
            high=round(high_val, 2),
            low=round(low_val, 2),
            depth_pct=round(depth_pct, 2),
            avg_volume=round(avg_vol, 0),
        ))
        used_lows.add(best_low_idx)

        # Stop if we have enough contractions
        if len(contractions) >= 5:
            break

    return contractions


def _validate_contractions(contractions: list[Contraction]) -> bool:
    """Validate that contractions form a valid VCP pattern.

    Rules:
    - At least 2 contractions
    - T1 depth between 10% and 40%
    - Each subsequent contraction is smaller (diminishing with tolerance)
    - Overall pattern shows tightening
    """
    if len(contractions) < 2:
        return False

    # T1 must be between 10% and 40%
    t1_depth = contractions[0].depth_pct
    if t1_depth < 10 or t1_depth > 40:
        return False

    # Check diminishing pattern (allow some tolerance)
    diminishing_count = 0
    for i in range(1, len(contractions)):
        if contractions[i].depth_pct < contractions[i - 1].depth_pct:
            diminishing_count += 1

    # At least half must be diminishing (tolerance for noise)
    if diminishing_count < (len(contractions) - 1) * 0.5:
        return False

    # Last contraction must be significantly smaller than first
    last_depth = contractions[-1].depth_pct
    if last_depth >= t1_depth * 0.85:  # Must be at least 15% smaller
        return False

    return True


def _calculate_score(
    contractions: list[Contraction],
    volume_dry_ratio: float,
    rs_percentile: float,
    base_df: pd.DataFrame,
) -> int:
    """Calculate VCP quality score (0-100).

    Dimensions:
    - Contraction smoothness (20%): How consistently contractions diminish
    - Volume dry-up (20%): How much volume dried up in last contraction
    - Base duration (15%): 5-15 weeks is optimal
    - RS rating (20%): Higher RS = better
    - Final tightness (15%): How tight the last contraction is
    - Contraction count (10%): 3-4 is optimal
    """
    score = 0.0

    # 1. Contraction smoothness (20 pts)
    if len(contractions) >= 2:
        ratios = []
        for i in range(1, len(contractions)):
            if contractions[i - 1].depth_pct > 0:
                ratios.append(contractions[i].depth_pct / contractions[i - 1].depth_pct)
        if ratios:
            avg_ratio = np.mean(ratios)
            # Ideal ratio is 0.4-0.6 (each contraction 40-60% of previous)
            if 0.3 <= avg_ratio <= 0.7:
                score += 20
            elif 0.2 <= avg_ratio <= 0.8:
                score += 14
            else:
                score += 7

    # 2. Volume dry-up (20 pts)
    if volume_dry_ratio <= 0.4:
        score += 20
    elif volume_dry_ratio <= 0.6:
        score += 15
    elif volume_dry_ratio <= 0.8:
        score += 8

    # 3. Base duration (15 pts) - 5 to 15 weeks (25-75 trading days)
    base_days = len(base_df)
    if 25 <= base_days <= 75:
        score += 15
    elif 15 <= base_days <= 100:
        score += 10
    elif base_days > 5:
        score += 5

    # 4. RS rating (20 pts)
    if rs_percentile >= 90:
        score += 20
    elif rs_percentile >= 80:
        score += 16
    elif rs_percentile >= 70:
        score += 12
    elif rs_percentile >= 60:
        score += 6

    # 5. Final tightness (15 pts) - last contraction depth
    last_depth = contractions[-1].depth_pct
    if last_depth < 8:
        score += 15
    elif last_depth < 12:
        score += 10
    elif last_depth < 15:
        score += 5

    # 6. Contraction count (10 pts)
    count = len(contractions)
    if count in (3, 4):
        score += 10
    elif count == 2:
        score += 6
    elif count == 5:
        score += 7

    return min(100, int(round(score)))
