"""内置回测策略"""
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import List


class BaseStrategy(ABC):
    """策略基类"""
    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        Returns: Series with values: 1 (买入), -1 (卖出), 0 (持有)
        """
        pass


class MACrossStrategy(BaseStrategy):
    """均线交叉策略 (MA5/MA20 金叉买入，死叉卖出)"""
    name = "均线交叉"

    def __init__(self, short: int = 5, long: int = 20):
        self.short = short
        self.long = long

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma_short = df['Close'].rolling(window=self.short).mean()
        ma_long = df['Close'].rolling(window=self.long).mean()

        signals = pd.Series(0, index=df.index)
        # 金叉: 短均线上穿长均线
        signals[(ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))] = 1
        # 死叉: 短均线下穿长均线
        signals[(ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))] = -1
        return signals


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""
    name = "RSI"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=df.index)
        # RSI 从超卖区回升 -> 买入
        signals[(rsi > self.oversold) & (rsi.shift(1) <= self.oversold)] = 1
        # RSI 从超买区回落 -> 卖出
        signals[(rsi < self.overbought) & (rsi.shift(1) >= self.overbought)] = -1
        return signals


class MACDStrategy(BaseStrategy):
    """MACD 金叉死叉策略"""
    name = "MACD"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()

        signals = pd.Series(0, index=df.index)
        signals[(dif > dea) & (dif.shift(1) <= dea.shift(1))] = 1
        signals[(dif < dea) & (dif.shift(1) >= dea.shift(1))] = -1
        return signals


class BollingerStrategy(BaseStrategy):
    """布林带突破策略"""
    name = "布林带"

    def __init__(self, period: int = 20, std_dev: float = 2):
        self.period = period
        self.std_dev = std_dev

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        middle = df['Close'].rolling(window=self.period).mean()
        std = df['Close'].rolling(window=self.period).std()
        upper = middle + (std * self.std_dev)
        lower = middle - (std * self.std_dev)

        signals = pd.Series(0, index=df.index)
        # 价格触及下轨后回升 -> 买入
        signals[(df['Close'] > lower) & (df['Close'].shift(1) <= lower.shift(1))] = 1
        # 价格触及上轨后回落 -> 卖出
        signals[(df['Close'] < upper) & (df['Close'].shift(1) >= upper.shift(1))] = -1
        return signals


# 策略注册表
STRATEGIES = {
    "均线交叉": MACrossStrategy,
    "ma": MACrossStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "布林带": BollingerStrategy,
    "bollinger": BollingerStrategy,
}


def get_strategy(name: str) -> BaseStrategy:
    """根据名称获取策略实例"""
    name_lower = name.lower()
    cls = STRATEGIES.get(name_lower) or STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(STRATEGIES.keys())
        raise ValueError(f"未知策略: {name}\n可用策略: {available}")
    return cls()
