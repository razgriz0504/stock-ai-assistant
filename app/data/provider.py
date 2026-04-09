from abc import ABC, abstractmethod
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class Quote:
    """实时报价"""
    symbol: str
    price: float
    change: float       # 涨跌额
    change_pct: float   # 涨跌幅 %
    high: float
    low: float
    volume: int
    timestamp: str


class DataProvider(ABC):
    """数据源抽象接口"""

    @abstractmethod
    def get_realtime_quote(self, symbol: str) -> Optional[Quote]:
        """获取实时报价"""
        pass

    @abstractmethod
    def get_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        获取历史K线数据

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            Index: DatetimeIndex
        """
        pass
