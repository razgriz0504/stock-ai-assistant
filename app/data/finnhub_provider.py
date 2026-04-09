import logging
import finnhub
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from config import settings
from app.data.provider import DataProvider, Quote

logger = logging.getLogger(__name__)


class FinnhubProvider(DataProvider):
    """Finnhub 数据源 - 主要用于实时监控报价"""

    def __init__(self):
        api_key = settings.finnhub_api_key
        if not api_key:
            logger.warning("Finnhub API key not set, provider will be unavailable")
            self._client = None
        else:
            self._client = finnhub.Client(api_key=api_key)

    def get_realtime_quote(self, symbol: str) -> Optional[Quote]:
        if not self._client:
            logger.warning("Finnhub client not initialized")
            return None

        try:
            q = self._client.quote(symbol.upper())
            if not q or q.get("c", 0) == 0:
                return None

            return Quote(
                symbol=symbol.upper(),
                price=round(q["c"], 2),       # current price
                change=round(q["d"], 2),       # change
                change_pct=round(q["dp"], 2),  # change percent
                high=round(q["h"], 2),         # high
                low=round(q["l"], 2),          # low
                volume=0,                       # quote endpoint doesn't include volume
                timestamp=datetime.fromtimestamp(q["t"]).isoformat() if q.get("t") else "",
            )
        except Exception as e:
            logger.error(f"Finnhub quote error for {symbol}: {e}")
            return None

    def get_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Finnhub 历史数据（candles endpoint）"""
        if not self._client:
            return pd.DataFrame()

        period_map = {
            "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825,
        }
        days = period_map.get(period, 365)
        end = datetime.now()
        start = end - timedelta(days=days)

        try:
            res = self._client.stock_candles(
                symbol.upper(), "D",
                int(start.timestamp()),
                int(end.timestamp()),
            )
            if res.get("s") != "ok":
                return pd.DataFrame()

            df = pd.DataFrame({
                "Open": res["o"],
                "High": res["h"],
                "Low": res["l"],
                "Close": res["c"],
                "Volume": res["v"],
            }, index=pd.to_datetime(res["t"], unit="s"))
            df.index.name = "Date"
            return df
        except Exception as e:
            logger.error(f"Finnhub history error for {symbol}: {e}")
            return pd.DataFrame()
