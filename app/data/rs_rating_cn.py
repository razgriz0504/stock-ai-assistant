"""A 股 RS (Relative Strength) Percentile - 宇宙内百分位排名.

对齐美股 rs_rating.py 的接口 (get_rs_snapshot / compute_rs_snapshot),
采用 IBD 加权多周期算法（交易日近似）:
- RS raw = 0.4×63日 + 0.2×126日 + 0.2×189日 + 0.2×252日 涨幅
- 再在全 Universe 中排百分位（0-100）
- 数据源: akshare 而非 yfinance
- 缓存独立于美股, TTL 24h

与美股 rs_rating.py 完全一致的加权逻辑，差异仅在于数据源。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_rs_cache: dict[str, float] = {}
_rs_cache_ts: float = 0.0
_RS_CACHE_TTL = 86400  # 24 hours


def _fetch_close_history(symbol: str, start_date: str, end_date: str) -> Optional[pd.Series]:
    """拉单只收盘价 (前复权). 返回 Series(index=Date, name=symbol).

    数据源: akshare stock_zh_a_daily (网易163), 比 stock_zh_a_hist (东财) 更稳定.
    """
    try:
        import akshare as ak
        code = symbol.zfill(6)
        # sh/sz 前缀
        prefix = "sh" if code.startswith("6") else "sz"
        sym_163 = f"{prefix}{code}"

        raw = ak.stock_zh_a_daily(symbol=sym_163, adjust="qfq")
        if raw is None or raw.empty:
            return None

        s = pd.to_numeric(raw["close"], errors="coerce")
        s.index = pd.to_datetime(raw["date"])
        s = s.dropna()
        s = s[s > 0]

        # 截取日期范围
        s = s[(s.index >= pd.Timestamp(start_date)) & (s.index <= pd.Timestamp(end_date))]

        # 至少需要 200 个有效交易日数据，确保 252 日涨幅计算可靠
        if len(s) < 200:
            return None
        s.name = code
        return s
    except Exception as e:
        logger.debug(f"RS fetch {symbol} failed: {e}")
        return None


def compute_rs_snapshot_cn(universe: list[str], max_workers: int = 12) -> dict[str, float]:
    """计算 A 股 universe 的 RS Percentile (0-100).

    与美股 rs_rating.py 完全一致:
    - IBD 加权多周期: 0.4×63日 + 0.2×126日 + 0.2×189日 + 0.2×252日 涨幅
    - 加权复合收益 → universe 内 rank pct → *100
    - 至少要有最近一季（63 日）数据才参与排名
    """
    global _rs_cache, _rs_cache_ts

    if not universe:
        return {}

    logger.info(f"Computing CN RS percentile for {len(universe)} stocks...")
    start_time = time.time()

    end = datetime.now()
    start = end - timedelta(days=460)  # ~15 个月, 保证 252 交易日窗口
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    closes: dict[str, pd.Series] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_close_history, s, start_str, end_str): s
            for s in universe
        }
        done = 0
        for fut in as_completed(futures):
            sym = futures[fut]
            s = fut.result()
            if s is not None:
                closes[sym] = s
            done += 1
            if done % 100 == 0:
                logger.info(f"CN RS fetch progress: {done}/{len(universe)}")

    if not closes:
        logger.warning("CN RS: no data collected")
        return _rs_cache if _rs_cache else {}

    # 拼成 DataFrame, 日期对齐
    close_df = pd.DataFrame(closes)
    close_df = close_df.sort_index()

    if len(close_df) < 200:
        logger.warning(f"CN RS: insufficient rows ({len(close_df)})")
        return _rs_cache if _rs_cache else {}

    # ── IBD 加权多周期 RS 得分（与美股 rs_rating.py 完全一致）──
    # RS raw = 0.4×Q1 + 0.2×Q2 + 0.2×Q3 + 0.2×Q4 涨幅（交易日近似）
    # Q1 为最近一季（63 交易日），权重加倍，对刚启动的强势股更敏感。
    end_prices = close_df.iloc[-1]
    n_rows = len(close_df)

    windows = [(63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2)]
    weighted_sum = pd.Series(0.0, index=close_df.columns)
    weight_used = pd.Series(0.0, index=close_df.columns)
    q1_valid = pd.Series(False, index=close_df.columns)

    for lb, w in windows:
        if n_rows <= lb:
            continue
        start_prices = close_df.iloc[-(lb + 1)]
        valid_mask = (
            (start_prices > 0) & start_prices.notna()
            & (end_prices > 0) & end_prices.notna()
        )
        ret = (end_prices[valid_mask] / start_prices[valid_mask]) - 1
        weighted_sum[ret.index] += w * ret
        weight_used[ret.index] += w
        if lb == 63:
            q1_valid = valid_mask

    # 至少要有最近一季（63 日）数据才参与排名
    has_q1 = q1_valid & (weight_used > 0)
    scored = weighted_sum[has_q1] / weight_used[has_q1]

    if scored.empty:
        logger.warning("CN RS: no valid stocks for weighted return calculation")
        return _rs_cache if _rs_cache else {}

    # 百分位排名（0-100）
    rs_percentile = scored.rank(pct=True) * 100

    result = {sym: round(float(v), 2) for sym, v in rs_percentile.items() if pd.notna(v)}

    _rs_cache = result
    _rs_cache_ts = time.time()

    elapsed = time.time() - start_time
    logger.info(f"CN RS percentile computed: {len(result)} stocks in {elapsed:.1f}s")
    return result


def get_rs_snapshot_cn(universe: Optional[list[str]] = None) -> dict[str, float]:
    """带缓存的 RS 快照."""
    global _rs_cache, _rs_cache_ts

    now = time.time()
    if _rs_cache and (now - _rs_cache_ts) < _RS_CACHE_TTL:
        return _rs_cache

    if universe:
        return compute_rs_snapshot_cn(universe)

    if _rs_cache:
        logger.warning("CN RS cache expired but no universe provided, returning stale cache")
        return _rs_cache

    return {}


def invalidate_rs_cache_cn():
    global _rs_cache_ts
    _rs_cache_ts = 0.0
