"""AkshareProvider: A 股数据源, 对齐 YFinanceProvider 接口.

关键接口:
- get_history(symbol, period): 日线 OHLCV (前复权)
- get_batch_history: 并行批量拉取 (akshare 无原生批量, 线程池并发)
- get_batch_fundamentals: 基础信息 (股票名称/行业)
- get_realtime_quote: 实时快照

period 映射到起始日期偏移:
    1y  → 365 天
    2y  → 730 天
    15mo → 460 天
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from app.data.provider import DataProvider, Quote

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "1mo": 45,
    "3mo": 100,
    "6mo": 200,
    "1y": 365,
    "15mo": 460,
    "2y": 730,
    "3y": 1100,
    "5y": 1830,
}


def _code_to_163_symbol(code: str) -> str:
    """6位代码转 stock_zh_a_daily 所需的 sh/sz 前缀格式.

    规则: 6开头→sh, 0/3开头→sz, 其他→sz
    """
    code = code.zfill(6)
    if code.startswith("6"):
        return f"sh{code}"
    return f"sz{code}"

# Fundamental cache: 24h
_fundamental_cache: dict[str, dict] = {}
_FUNDAMENTAL_CACHE_TTL = 86400

# Spot quote cache: 60s (整表一次拉全市场)
_spot_cache: dict = {"data": None, "ts": 0.0}
_SPOT_CACHE_TTL = 60


def _period_to_dates(period: str) -> tuple[str, str]:
    """把 period 字符串转成 akshare 需要的 (start_date, end_date) yyyymmdd."""
    days = _PERIOD_DAYS.get(period, 365)
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _get_spot_df() -> Optional[pd.DataFrame]:
    """全市场实时快照 (60s 缓存). akshare stock_zh_a_spot_em."""
    now = time.time()
    if _spot_cache["data"] is not None and (now - _spot_cache["ts"]) < _SPOT_CACHE_TTL:
        return _spot_cache["data"]

    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return None
        # 代码列标准化
        if "代码" in df.columns:
            df["代码"] = df["代码"].astype(str).str.zfill(6)
        _spot_cache["data"] = df
        _spot_cache["ts"] = now
        return df
    except Exception as e:
        logger.warning(f"stock_zh_a_spot_em failed: {e}")
        return None


class AkshareProvider(DataProvider):
    """akshare 数据源 (A 股)."""

    def get_realtime_quote(self, symbol: str) -> Optional[Quote]:
        """实时报价. 从全市场快照表提取 (60s 缓存, 单只查询开销 O(1))."""
        try:
            df = _get_spot_df()
            if df is None:
                return None
            code = symbol.zfill(6)
            row_matches = df[df["代码"] == code]
            if row_matches.empty:
                return None
            row = row_matches.iloc[0]

            price = float(row.get("最新价", 0))
            change_pct = float(row.get("涨跌幅", 0))
            change = float(row.get("涨跌额", 0))
            high = float(row.get("最高", price))
            low = float(row.get("最低", price))
            volume = int(row.get("成交量", 0))

            return Quote(
                symbol=code,
                price=round(price, 2),
                change=round(change, 2),
                change_pct=round(change_pct, 2),
                high=round(high, 2),
                low=round(low, 2),
                volume=volume,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.debug(f"akshare quote error for {symbol}: {e}")
            return None

    def get_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """日线 OHLCV, 前复权. 列名对齐 yfinance: [Open, High, Low, Close, Volume] + DatetimeIndex.

        数据源: akshare stock_zh_a_daily (网易163), 比 stock_zh_a_hist (东财) 更稳定.
        """
        try:
            import akshare as ak
            sym_163 = _code_to_163_symbol(symbol)
            raw = ak.stock_zh_a_daily(symbol=sym_163, adjust="qfq")
            if raw is None or raw.empty:
                return pd.DataFrame()

            # 列名: date, open, high, low, close, volume, ...
            df = pd.DataFrame({
                "Open": pd.to_numeric(raw["open"], errors="coerce"),
                "High": pd.to_numeric(raw["high"], errors="coerce"),
                "Low": pd.to_numeric(raw["low"], errors="coerce"),
                "Close": pd.to_numeric(raw["close"], errors="coerce"),
                "Volume": pd.to_numeric(raw["volume"], errors="coerce"),
            })
            df.index = pd.to_datetime(raw["date"])
            df = df.dropna(subset=["Close"])
            df = df[df["Close"] > 0]

            # 按 period 截取日期范围
            days = _PERIOD_DAYS.get(period, 365)
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df.index >= pd.Timestamp(cutoff)]

            return df
        except Exception as e:
            logger.debug(f"akshare history error for {symbol}: {e}")
            return pd.DataFrame()

    def get_batch_history(
        self, symbols: list[str], period: str = "1y", max_workers: int = 12
    ) -> dict[str, pd.DataFrame]:
        """并行批量拉取. A 股 ~800 只, 12 并发, 单次耗时 ~5-8 分钟."""
        if not symbols:
            return {}

        result: dict[str, pd.DataFrame] = {}
        start_ts = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.get_history, s, period): s for s in symbols}
            done_count = 0
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    df = fut.result()
                    if not df.empty and len(df) >= 5:
                        result[sym] = df
                except Exception as e:
                    logger.debug(f"batch history failed for {sym}: {e}")
                done_count += 1
                if done_count % 100 == 0:
                    logger.info(f"CN batch history progress: {done_count}/{len(symbols)}")

        elapsed = time.time() - start_ts
        logger.info(
            f"CN batch history: {len(result)}/{len(symbols)} loaded in {elapsed:.1f}s"
        )
        return result

    def get_fundamental_info(self, symbol: str) -> dict:
        """基础信息: 股票名称, 行业, 市值等. akshare stock_individual_info_em."""
        now = time.time()
        cached = _fundamental_cache.get(symbol)
        if cached and (now - cached["ts"]) < _FUNDAMENTAL_CACHE_TTL:
            return cached["data"]

        info_data: dict = {}
        try:
            import akshare as ak
            code = symbol.zfill(6)
            df = ak.stock_individual_info_em(symbol=code)
            if df is not None and not df.empty:
                # df 是 (item, value) 长表
                kv = dict(zip(df["item"].astype(str), df["value"]))
                info_data = {
                    "short_name": str(kv.get("股票简称", "")).strip(),
                    "sector": str(kv.get("行业", "")).strip(),
                    "industry": str(kv.get("行业", "")).strip(),
                    "market_cap": _to_float(kv.get("总市值")),
                    "float_market_cap": _to_float(kv.get("流通市值")),
                    "pe_ratio": None,
                    "forward_pe": None,
                    "pb_ratio": None,
                    "revenue_growth": None,
                    "earnings_growth": None,
                    "roe": None,
                    "dividend_yield": None,
                    "fifty_two_week_high": None,
                    "fifty_two_week_low": None,
                }
        except Exception as e:
            logger.debug(f"akshare fundamental for {symbol}: {e}")

        _fundamental_cache[symbol] = {"data": info_data, "ts": now}
        return info_data

    def get_batch_fundamentals(
        self, symbols: list[str], max_workers: int = 10
    ) -> dict[str, dict]:
        """并行批量拉取基础信息."""
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.get_fundamental_info, s): s for s in symbols}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    results[sym] = fut.result()
                except Exception as e:
                    logger.debug(f"batch fundamentals error for {sym}: {e}")
                    results[sym] = {}
        return results


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
