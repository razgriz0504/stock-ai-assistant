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
    status: str             # "forming" / "breakout" / "extended" / "failed"
    score: int              # 0-100 quality score
    pivot_price: float      # The breakout pivot point
    base_start_date: str    # When the base started
    contractions: list[Contraction] = field(default_factory=list)
    volume_dry_ratio: float = 0.0   # Last contraction vol / base avg vol
    breakout_volume_surge: bool = False  # 当 status=breakout 时, 当日量能是否 > 1.5x SMA20


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

        # ── Status 判定: 价格驱动 (Price Action 优先), 量能作为辅助标记 ──
        # 修复: 不再用 volume 作为 breakout 硬门槛, 避免错过缩量回踩 Pivot 的 Cheat 进场点
        volume_surge = last_volume > 1.5 * vol_sma20
        if last_close > pivot_price:
            extension_pct = (last_close - pivot_price) / pivot_price * 100
            if extension_pct > 5.0:
                status = "extended"  # 已超 pivot 5%, 错过买点
            else:
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
            breakout_volume_surge=bool(volume_surge and status == "breakout"),
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
        # 冗余防御: 即便 len>=10, 切片后仍显式校验, 防止停牌/次新股边界异常
        tail = subsequent[5:]
        if len(tail) == 0:
            continue
        min_after = tail.min()
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
    """重构版: 基于时间序状态机的严格交替高低点提取.

    旧实现遍历 swing_high_indices 配对下一个未使用的 swing_low, 在连续出现
    多个邻近 HIGH (H1, H2, L1) 时会破坏波段交替结构. 新实现按时间序合并所
    有极值事件, 用状态机强制 HIGH -> LOW 交替: 等待 LOW 期间若再现更高 HIGH
    则动态上移基底高点, 出现 LOW 则配对并复位状态.
    """
    small_window = 4
    highs = base_df["High"].values
    lows = base_df["Low"].values
    volumes = base_df["Volume"].values
    dates = base_df.index
    n = len(base_df)

    if n < 15:
        return []

    # 1. 提取所有局部极值点, 按时间序合并
    events = []  # (index, type, price)
    for i in range(small_window, n - small_window):
        left_s = max(0, i - small_window)
        right_e = min(n, i + small_window + 1)
        if highs[i] == highs[left_s:right_e].max():
            events.append((i, "HIGH", float(highs[i])))
        if lows[i] == lows[left_s:right_e].min():
            events.append((i, "LOW", float(lows[i])))

    if not events:
        return []

    # events 按 index 排序 (同 index 时 HIGH 优先, 避免同 bar 同时为高低点导致空段)
    events.sort(key=lambda e: (e[0], 0 if e[1] == "HIGH" else 1))

    # 2. 状态机: 强制 HIGH -> LOW 交替
    contractions: list[Contraction] = []
    last_high_idx: Optional[int] = None
    last_high_val: Optional[float] = None

    for idx, ev_type, price in events:
        if ev_type == "HIGH":
            # 等待 LOW 期间出现更高 HIGH, 动态上移基底
            if last_high_val is None or price > last_high_val:
                last_high_idx = idx
                last_high_val = price
        elif ev_type == "LOW" and last_high_idx is not None:
            sh_idx = last_high_idx
            sl_idx = idx
            if sl_idx <= sh_idx:
                continue

            high_val = float(last_high_val)
            low_val = float(lows[sl_idx])
            if high_val <= 0:
                continue

            depth_pct = (high_val - low_val) / high_val * 100
            vol_slice = volumes[sh_idx:sl_idx + 1]
            avg_vol = float(vol_slice.mean()) if len(vol_slice) > 0 else 0.0

            contractions.append(Contraction(
                name=f"T{len(contractions) + 1}",
                start_date=str(dates[sh_idx].date()),
                end_date=str(dates[sl_idx].date()),
                high=round(high_val, 2),
                low=round(low_val, 2),
                depth_pct=round(depth_pct, 2),
                avg_volume=round(avg_vol, 0),
            ))

            # 复位状态, 等待下一个 HIGH
            last_high_idx = None
            last_high_val = None

            if len(contractions) >= 5:
                break

    return contractions


def _validate_contractions(contractions: list[Contraction]) -> bool:
    """Validate that contractions form a valid VCP pattern.

    Rules:
    - At least 2 contractions
    - T1 depth between 10% and 40%
    - Strict monotonic decrease with ±1% tolerance (no expansion allowed)
    - Last contraction must be < 5% (筹码锁死)
    - Overall pattern shows clear tightening (last < 50% of first)
    """
    if len(contractions) < 2:
        return False

    # T1 must be between 10% and 40%
    t1_depth = contractions[0].depth_pct
    if t1_depth < 10 or t1_depth > 40:
        return False

    # ── Strict monotonic decrease check ──
    # Each contraction must be <= previous + tolerance (1%)
    # Allow AT MOST one violation across the entire sequence
    TOLERANCE_PCT = 1.0  # Allow 1% overshoot
    violations = 0
    for i in range(1, len(contractions)):
        # 显式 round 规避浮点精度残留 (0.1 + 0.2 != 0.3 类问题)
        curr = round(contractions[i].depth_pct, 2)
        prev = round(contractions[i - 1].depth_pct, 2)
        if curr > round(prev + TOLERANCE_PCT, 2):
            violations += 1

    # Zero tolerance for expansion when we have few contractions
    # Allow 1 violation only if we have 4+ contractions
    max_allowed_violations = 1 if len(contractions) >= 4 else 0
    if violations > max_allowed_violations:
        return False

    # ── Last contraction must be tight (< 5%) ──
    last_depth = contractions[-1].depth_pct
    if last_depth >= 5.0:
        return False

    # ── Overall tightening: last must be < 50% of first ──
    if last_depth >= t1_depth * 0.50:
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
    if last_depth < 2:
        score += 15
    elif last_depth < 3:
        score += 12
    elif last_depth < 4:
        score += 8
    elif last_depth < 5:
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
