"""RS (Relative Strength) Percentile Rating - 向量化预计算模块.

将全 Universe 的 252 日涨幅在全市场中排百分位（0-100），
结果缓存于内存，TTL 24h，定时任务每日收盘后刷新。
"""

import time
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── 缓存 ──
_rs_cache: dict[str, float] = {}
_rs_cache_ts: float = 0.0
_RS_CACHE_TTL = 86400  # 24 hours


def compute_rs_snapshot(universe: list[str]) -> dict[str, float]:
    """计算全 Universe 的 RS Percentile（0-100）.

    核心逻辑：
    1. 批量下载 universe 过去 ~260 交易日的收盘价
    2. 计算每只股票 252 日涨幅
    3. 在全 universe 中排百分位
    """
    global _rs_cache, _rs_cache_ts

    if not universe:
        return {}

    logger.info(f"Computing RS percentile for {len(universe)} stocks...")
    start_time = time.time()

    try:
        # 批量下载 1 年+缓冲 的收盘价（确保有 252 个交易日）
        data = yf.download(
            universe,
            period="15mo",
            progress=False,
            threads=True,
        )

        if data.empty:
            logger.warning("RS computation: yf.download returned empty data")
            return _rs_cache if _rs_cache else {}

        # 提取 Close 价格
        if isinstance(data.columns, pd.MultiIndex):
            # 多只股票: columns = (Price, Ticker) 或 (Ticker, Price)
            level0_vals = set(data.columns.get_level_values(0).unique())
            batch_set = set(universe)
            level0_overlap = len(level0_vals & batch_set)

            if level0_overlap > len(universe) * 0.3:
                # Level 0 is ticker
                close_df = data.xs("Close", level=1, axis=1) if "Close" in set(data.columns.get_level_values(1)) else None
                if close_df is None:
                    # Try alternative structure
                    close_df = pd.DataFrame({
                        sym: data[sym]["Close"] for sym in universe
                        if sym in level0_vals
                    })
            else:
                # Level 0 is Price type (standard format)
                if "Close" in level0_vals:
                    close_df = data["Close"]
                else:
                    close_df = data.xs("Close", level=0, axis=1)
        else:
            # 单只股票
            if "Close" in data.columns:
                close_df = data[["Close"]]
                close_df.columns = [universe[0]]
            else:
                logger.warning("RS computation: cannot extract Close prices")
                return _rs_cache if _rs_cache else {}

        # 确保 close_df 是 DataFrame
        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame()

        # 删掉全 NaN 的列（股票没数据）
        close_df = close_df.dropna(axis=1, how="all")

        if close_df.empty or len(close_df) < 200:
            logger.warning(f"RS computation: insufficient data rows ({len(close_df)})")
            return _rs_cache if _rs_cache else {}

        # 向量化计算 252 日涨幅（用可用的最长跨度，至少 200 天）
        lookback = min(252, len(close_df) - 1)
        start_prices = close_df.iloc[-(lookback + 1)]
        end_prices = close_df.iloc[-1]

        # 过滤掉起始或结束价为 NaN/0 的
        valid_mask = (start_prices > 0) & (end_prices > 0) & start_prices.notna() & end_prices.notna()
        start_valid = start_prices[valid_mask]
        end_valid = end_prices[valid_mask]

        if start_valid.empty:
            logger.warning("RS computation: no valid stocks for return calculation")
            return _rs_cache if _rs_cache else {}

        # 一步计算 252 日涨幅
        returns_252d = (end_valid / start_valid) - 1

        # 百分位排名（0-100）
        rs_percentile = returns_252d.rank(pct=True) * 100

        # 转为 dict
        result = {sym: round(float(val), 2) for sym, val in rs_percentile.items() if pd.notna(val)}

        # 更新缓存
        _rs_cache = result
        _rs_cache_ts = time.time()

        elapsed = time.time() - start_time
        logger.info(f"RS percentile computed: {len(result)} stocks in {elapsed:.1f}s")
        return result

    except Exception as e:
        logger.error(f"RS computation failed: {e}", exc_info=True)
        return _rs_cache if _rs_cache else {}


def get_rs_snapshot(universe: Optional[list[str]] = None) -> dict[str, float]:
    """获取 RS Percentile 快照（带缓存）.

    如果缓存有效（< 24h），直接返回缓存。
    否则触发重新计算。
    """
    global _rs_cache, _rs_cache_ts

    now = time.time()
    if _rs_cache and (now - _rs_cache_ts) < _RS_CACHE_TTL:
        return _rs_cache

    if universe:
        return compute_rs_snapshot(universe)

    # 缓存过期且没有传入 universe，返回过期缓存（好过空）
    if _rs_cache:
        logger.warning("RS cache expired but no universe provided, returning stale cache")
        return _rs_cache

    return {}


def invalidate_rs_cache():
    """手动使缓存失效（用于强制刷新）"""
    global _rs_cache_ts
    _rs_cache_ts = 0.0
