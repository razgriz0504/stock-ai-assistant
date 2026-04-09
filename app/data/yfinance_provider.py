import logging
import yfinance as yf
import pandas as pd
from typing import Optional

from app.data.provider import DataProvider, Quote

logger = logging.getLogger(__name__)


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
