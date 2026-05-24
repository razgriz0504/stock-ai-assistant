import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf
import pandas as pd
from typing import Optional

from app.data.provider import DataProvider, Quote

logger = logging.getLogger(__name__)

# Fundamental data cache: {symbol: {"data": dict, "ts": float}}
_fundamental_cache: dict[str, dict] = {}
_FUNDAMENTAL_CACHE_TTL = 86400  # 24h


class YFinanceProvider(DataProvider):
    """yfinance 数据源 - 主要用于历史回测数据"""

    def get_realtime_quote(self, symbol: str) -> Optional[Quote]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            hist = ticker.history(period="2d")
            if hist.empty:
                return None

            current = hist.iloc[-1]
            prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else current["Close"]
            change = current["Close"] - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            return Quote(
                symbol=symbol.upper(),
                price=round(current["Close"], 2),
                change=round(change, 2),
                change_pct=round(change_pct, 2),
                high=round(current["High"], 2),
                low=round(current["Low"], 2),
                volume=int(current["Volume"]),
                timestamp=str(current.name),
            )
        except Exception as e:
            logger.error(f"yfinance quote error for {symbol}: {e}")
            return None

    def get_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty:
                logger.warning(f"yfinance returned empty data for {symbol}")
            return df
        except Exception as e:
            logger.error(f"yfinance history error for {symbol}: {e}")
            return pd.DataFrame()

    def get_batch_history(self, symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
        """Batch download historical data for multiple symbols.

        Uses yf.download for efficient batch fetching. Returns dict of {symbol: DataFrame}.
        """
        if not symbols:
            return {}

        result: dict[str, pd.DataFrame] = {}
        batch_size = 50

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            try:
                data = yf.download(
                    batch,
                    period=period,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                if data.empty:
                    continue

                if len(batch) == 1:
                    sym = batch[0]
                    if not data.empty:
                        df = data.copy()
                        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                        result[sym] = df
                else:
                    for sym in batch:
                        try:
                            if sym in data.columns.get_level_values(0):
                                df = data[sym].dropna(how="all")
                                if not df.empty:
                                    result[sym] = df
                        except (KeyError, TypeError):
                            continue
            except Exception as e:
                logger.warning(f"Batch download failed for chunk {i}-{i+len(batch)}: {e}")
                for sym in batch:
                    df = self.get_history(sym, period)
                    if not df.empty:
                        result[sym] = df

        logger.info(f"Batch history: requested {len(symbols)}, got {len(result)}")
        return result

    def get_fundamental_info(self, symbol: str) -> dict:
        """Get fundamental data for a symbol (cached 24h)."""
        now = time.time()
        cached = _fundamental_cache.get(symbol)
        if cached and (now - cached["ts"]) < _FUNDAMENTAL_CACHE_TTL:
            return cached["data"]

        info_data = {}
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            info_data = {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "revenue_growth": _to_pct(info.get("revenueGrowth")),
                "earnings_growth": _to_pct(info.get("earningsGrowth")),
                "roe": _to_pct(info.get("returnOnEquity")),
                "dividend_yield": _to_pct(info.get("dividendYield")),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
            }
        except Exception as e:
            logger.debug(f"Fundamental fetch failed for {symbol}: {e}")

        _fundamental_cache[symbol] = {"data": info_data, "ts": now}
        return info_data

    def get_batch_fundamentals(self, symbols: list[str], max_workers: int = 10) -> dict[str, dict]:
        """Fetch fundamental data for multiple symbols in parallel."""
        results: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.get_fundamental_info, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    logger.debug(f"Fundamental error for {sym}: {e}")
                    results[sym] = {}

        return results


def _to_pct(value) -> Optional[float]:
    """Convert ratio (0.15) to percentage (15.0), returns None if invalid."""
    if value is None:
        return None
    try:
        return round(float(value) * 100, 2)
    except (ValueError, TypeError):
        return None
