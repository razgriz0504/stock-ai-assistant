"""
美股股票量价趋势分析器
复用自现有 stock_analysis.py，移除代理配置，适配服务端调用
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from app.data.yfinance_provider import YFinanceProvider

_yf_provider = YFinanceProvider()


class StockAnalyzer:
    """股票量价趋势分析器"""

    def __init__(self, symbol: str, period: str = "1y"):
        self.symbol = symbol.upper()
        self.period = period
        self.data = None
        self.indicators = {}
        self.signals = {}
        self.stock_name = self.symbol

    def fetch_data(self) -> pd.DataFrame:
        self.data = _yf_provider.get_history(self.symbol, self.period)
        if self.data.empty:
            raise ValueError(f"无法获取 {self.symbol} 的数据，请检查股票代码是否正确")
        return self.data

    # ==================== 技术指标计算 ====================

    def calculate_ma(self, periods: list = None):
        if periods is None:
            periods = [5, 10, 20, 60, 120]
        for period in periods:
            self.data[f'MA{period}'] = self.data['Close'].rolling(window=period).mean()
        self.indicators['MA'] = periods

    def calculate_ema(self, periods: list = None):
        if periods is None:
            periods = [12, 26]
        for period in periods:
            self.data[f'EMA{period}'] = self.data['Close'].ewm(span=period, adjust=False).mean()
        self.indicators['EMA'] = periods

    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = self.data['Close'].ewm(span=fast, adjust=False).mean()
        ema_slow = self.data['Close'].ewm(span=slow, adjust=False).mean()
        self.data['MACD_DIF'] = ema_fast - ema_slow
        self.data['MACD_DEA'] = self.data['MACD_DIF'].ewm(span=signal, adjust=False).mean()
        self.data['MACD_Histogram'] = 2 * (self.data['MACD_DIF'] - self.data['MACD_DEA'])
        self.indicators['MACD'] = {'fast': fast, 'slow': slow, 'signal': signal}

    def calculate_rsi(self, period: int = 14):
        delta = self.data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        self.data['RSI'] = 100 - (100 / (1 + rs))
        self.indicators['RSI'] = period

    def calculate_kdj(self, n: int = 9, m1: int = 3, m2: int = 3):
        low_min = self.data['Low'].rolling(window=n).min()
        high_max = self.data['High'].rolling(window=n).max()
        rsv = (self.data['Close'] - low_min) / (high_max - low_min) * 100
        self.data['K'] = rsv.ewm(com=m1-1, adjust=False).mean()
        self.data['D'] = self.data['K'].ewm(com=m2-1, adjust=False).mean()
        self.data['J'] = 3 * self.data['K'] - 2 * self.data['D']
        self.indicators['KDJ'] = {'n': n, 'm1': m1, 'm2': m2}

    def calculate_bollinger_bands(self, period: int = 20, std_dev: int = 2):
        self.data['BB_Middle'] = self.data['Close'].rolling(window=period).mean()
        std = self.data['Close'].rolling(window=period).std()
        self.data['BB_Upper'] = self.data['BB_Middle'] + (std * std_dev)
        self.data['BB_Lower'] = self.data['BB_Middle'] - (std * std_dev)
        self.data['BB_Width'] = (self.data['BB_Upper'] - self.data['BB_Lower']) / self.data['BB_Middle']
        self.indicators['Bollinger'] = {'period': period, 'std_dev': std_dev}

    def calculate_volume_indicators(self):
        self.data['Volume_MA5'] = self.data['Volume'].rolling(window=5).mean()
        self.data['Volume_MA20'] = self.data['Volume'].rolling(window=20).mean()
        self.data['Volume_Ratio'] = self.data['Volume'] / self.data['Volume_MA20']

        obv = [0]
        for i in range(1, len(self.data)):
            if self.data['Close'].iloc[i] > self.data['Close'].iloc[i-1]:
                obv.append(obv[-1] + self.data['Volume'].iloc[i])
            elif self.data['Close'].iloc[i] < self.data['Close'].iloc[i-1]:
                obv.append(obv[-1] - self.data['Volume'].iloc[i])
            else:
                obv.append(obv[-1])
        self.data['OBV'] = obv

        self.data['VWAP'] = (
            self.data['Volume'] * (self.data['High'] + self.data['Low'] + self.data['Close']) / 3
        ).cumsum() / self.data['Volume'].cumsum()
        self.indicators['Volume'] = True

    def calculate_atr(self, period: int = 14):
        high_low = self.data['High'] - self.data['Low']
        high_close = np.abs(self.data['High'] - self.data['Close'].shift())
        low_close = np.abs(self.data['Low'] - self.data['Close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        self.data['ATR'] = true_range.rolling(window=period).mean()
        self.indicators['ATR'] = period

    def calculate_all_indicators(self):
        self.calculate_ma()
        self.calculate_ema()
        self.calculate_macd()
        self.calculate_rsi()
        self.calculate_kdj()
        self.calculate_bollinger_bands()
        self.calculate_volume_indicators()
        self.calculate_atr()

    # ==================== 趋势分析 ====================

    def analyze_ma_trend(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {
            'short_term': None, 'medium_term': None, 'long_term': None,
            'golden_cross': False, 'death_cross': False,
        }
        signals['short_term'] = 'bullish' if latest['MA5'] > latest['MA10'] else 'bearish'
        signals['medium_term'] = 'bullish' if latest['MA10'] > latest['MA20'] else 'bearish'

        if pd.notna(latest.get('MA60')):
            signals['long_term'] = 'bullish' if latest['MA20'] > latest['MA60'] else 'bearish'

        if len(self.data) >= 2:
            prev = self.data.iloc[-2]
            if prev['MA5'] <= prev['MA20'] and latest['MA5'] > latest['MA20']:
                signals['golden_cross'] = True
            elif prev['MA5'] >= prev['MA20'] and latest['MA5'] < latest['MA20']:
                signals['death_cross'] = True

        self.signals['MA'] = signals
        return signals

    def analyze_macd_trend(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {
            'dif_position': None, 'histogram_trend': None,
            'golden_cross': False, 'death_cross': False,
        }
        signals['dif_position'] = 'above_zero' if latest['MACD_DIF'] > 0 else 'below_zero'

        recent_hist = self.data['MACD_Histogram'].tail(5)
        signals['histogram_trend'] = 'increasing' if recent_hist.iloc[-1] > recent_hist.iloc[-2] else 'decreasing'

        if len(self.data) >= 2:
            prev = self.data.iloc[-2]
            if prev['MACD_DIF'] <= prev['MACD_DEA'] and latest['MACD_DIF'] > latest['MACD_DEA']:
                signals['golden_cross'] = True
            elif prev['MACD_DIF'] >= prev['MACD_DEA'] and latest['MACD_DIF'] < latest['MACD_DEA']:
                signals['death_cross'] = True

        self.signals['MACD'] = signals
        return signals

    def analyze_rsi(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {'level': None, 'divergence': None, 'value': latest['RSI']}

        if latest['RSI'] > 70:
            signals['level'] = 'overbought'
        elif latest['RSI'] < 30:
            signals['level'] = 'oversold'
        else:
            signals['level'] = 'neutral'

        recent = self.data.tail(20)
        if len(recent) >= 20:
            price_trend = recent['Close'].iloc[-1] > recent['Close'].iloc[0]
            rsi_trend = recent['RSI'].iloc[-1] > recent['RSI'].iloc[0]
            if price_trend and not rsi_trend:
                signals['divergence'] = 'bearish'
            elif not price_trend and rsi_trend:
                signals['divergence'] = 'bullish'

        self.signals['RSI'] = signals
        return signals

    def analyze_kdj(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {'level': None, 'golden_cross': False, 'death_cross': False, 'j_extreme': None}

        if latest['K'] > 80 and latest['D'] > 80:
            signals['level'] = 'overbought'
        elif latest['K'] < 20 and latest['D'] < 20:
            signals['level'] = 'oversold'
        else:
            signals['level'] = 'neutral'

        if latest['J'] > 100:
            signals['j_extreme'] = 'overbought'
        elif latest['J'] < 0:
            signals['j_extreme'] = 'oversold'

        if len(self.data) >= 2:
            prev = self.data.iloc[-2]
            if prev['K'] <= prev['D'] and latest['K'] > latest['D']:
                signals['golden_cross'] = True
            elif prev['K'] >= prev['D'] and latest['K'] < latest['D']:
                signals['death_cross'] = True

        self.signals['KDJ'] = signals
        return signals

    def analyze_bollinger(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {'position': None, 'squeeze': False, 'breakout': None}
        bb_percent = (latest['Close'] - latest['BB_Lower']) / (latest['BB_Upper'] - latest['BB_Lower'])

        if latest['Close'] > latest['BB_Upper']:
            signals['position'] = 'above_upper'
            signals['breakout'] = 'upward'
        elif latest['Close'] < latest['BB_Lower']:
            signals['position'] = 'below_lower'
            signals['breakout'] = 'downward'
        elif bb_percent > 0.8:
            signals['position'] = 'upper_zone'
        elif bb_percent < 0.2:
            signals['position'] = 'lower_zone'
        else:
            signals['position'] = 'middle_zone'

        recent_width = self.data['BB_Width'].tail(20)
        if latest['BB_Width'] < recent_width.mean() * 0.8:
            signals['squeeze'] = True

        self.signals['Bollinger'] = signals
        return signals

    def analyze_volume(self) -> dict:
        latest = self.data.iloc[-1]
        signals = {'volume_trend': None, 'price_volume_relation': None, 'volume_breakout': False}

        signals['volume_trend'] = 'increasing' if latest['Volume'] > latest['Volume_MA5'] else 'decreasing'
        signals['volume_breakout'] = latest['Volume_Ratio'] > 1.5

        price_change = (latest['Close'] - self.data.iloc[-2]['Close']) / self.data.iloc[-2]['Close']
        volume_change = (latest['Volume'] - self.data.iloc[-2]['Volume']) / self.data.iloc[-2]['Volume']

        if price_change > 0 and volume_change > 0:
            signals['price_volume_relation'] = 'price_up_volume_up'
        elif price_change > 0 and volume_change < 0:
            signals['price_volume_relation'] = 'price_up_volume_down'
        elif price_change < 0 and volume_change > 0:
            signals['price_volume_relation'] = 'price_down_volume_up'
        else:
            signals['price_volume_relation'] = 'price_down_volume_down'

        self.signals['Volume'] = signals
        return signals

    def analyze_all(self):
        self.analyze_ma_trend()
        self.analyze_macd_trend()
        self.analyze_rsi()
        self.analyze_kdj()
        self.analyze_bollinger()
        self.analyze_volume()

    # ==================== 投资建议生成 ====================

    def generate_recommendation(self) -> dict:
        bullish_signals = 0
        bearish_signals = 0
        details = []

        ma = self.signals.get('MA', {})
        if ma.get('short_term') == 'bullish':
            bullish_signals += 1; details.append("短期均线呈多头排列")
        else:
            bearish_signals += 1; details.append("短期均线呈空头排列")

        if ma.get('golden_cross'):
            bullish_signals += 2; details.append("出现均线金叉信号")
        if ma.get('death_cross'):
            bearish_signals += 2; details.append("出现均线死叉信号")

        macd = self.signals.get('MACD', {})
        if macd.get('dif_position') == 'above_zero':
            bullish_signals += 1; details.append("MACD在零轴上方运行")
        else:
            bearish_signals += 1; details.append("MACD在零轴下方运行")

        if macd.get('golden_cross'):
            bullish_signals += 2; details.append("MACD金叉")
        if macd.get('death_cross'):
            bearish_signals += 2; details.append("MACD死叉")

        if macd.get('histogram_trend') == 'increasing':
            bullish_signals += 1; details.append("MACD柱状图增长")
        else:
            bearish_signals += 1; details.append("MACD柱状图收缩")

        rsi = self.signals.get('RSI', {})
        if rsi.get('level') == 'overbought':
            bearish_signals += 1; details.append(f"RSI处于超买区域 ({rsi.get('value', 0):.1f})")
        elif rsi.get('level') == 'oversold':
            bullish_signals += 1; details.append(f"RSI处于超卖区域 ({rsi.get('value', 0):.1f})")

        if rsi.get('divergence') == 'bullish':
            bullish_signals += 2; details.append("RSI出现底背离")
        elif rsi.get('divergence') == 'bearish':
            bearish_signals += 2; details.append("RSI出现顶背离")

        kdj = self.signals.get('KDJ', {})
        if kdj.get('golden_cross'):
            bullish_signals += 1; details.append("KDJ金叉")
        if kdj.get('death_cross'):
            bearish_signals += 1; details.append("KDJ死叉")
        if kdj.get('j_extreme') == 'overbought':
            bearish_signals += 1; details.append("J值超买")
        elif kdj.get('j_extreme') == 'oversold':
            bullish_signals += 1; details.append("J值超卖")

        bb = self.signals.get('Bollinger', {})
        if bb.get('breakout') == 'upward':
            bullish_signals += 1; details.append("价格突破布林带上轨")
        elif bb.get('breakout') == 'downward':
            bearish_signals += 1; details.append("价格跌破布林带下轨")
        if bb.get('squeeze'):
            details.append("布林带收窄，可能即将变盘")

        vol = self.signals.get('Volume', {})
        if vol.get('price_volume_relation') == 'price_up_volume_up':
            bullish_signals += 1; details.append("量价配合良好，上涨有量支撑")
        elif vol.get('price_volume_relation') == 'price_down_volume_up':
            bearish_signals += 1; details.append("放量下跌，抛压较重")
        elif vol.get('price_volume_relation') == 'price_up_volume_down':
            details.append("缩量上涨，需警惕上涨动能不足")
        elif vol.get('price_volume_relation') == 'price_down_volume_down':
            details.append("缩量下跌，下跌动能减弱")

        total_weight = bullish_signals + bearish_signals
        score = (bullish_signals / total_weight) * 100 if total_weight > 0 else 50

        if score >= 70:
            recommendation = "买入"
            action_advice = "当前多项技术指标显示看涨信号，可以考虑逢低买入或加仓"
        elif score >= 55:
            recommendation = "谨慎看多"
            action_advice = "技术面偏多，但信号不够强烈，建议轻仓参与或持有观望"
        elif score >= 45:
            recommendation = "观望"
            action_advice = "多空信号交织，建议观望等待更明确的方向信号"
        elif score >= 30:
            recommendation = "谨慎看空"
            action_advice = "技术面偏空，建议减仓或暂不介入"
        else:
            recommendation = "卖出"
            action_advice = "多项技术指标显示看跌信号，建议减仓或止损"

        return {
            'score': score,
            'recommendation': recommendation,
            'action_advice': action_advice,
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals,
            'details': details,
        }

    # ==================== 报告生成 ====================

    def generate_report(self) -> str:
        latest = self.data.iloc[-1]
        prev = self.data.iloc[-2]
        price_change = (latest['Close'] - prev['Close']) / prev['Close'] * 100
        recommendation = self.generate_recommendation()

        lines = []
        lines.append(f"{'='*40}")
        lines.append(f"股票分析报告: {self.stock_name} ({self.symbol})")
        lines.append(f"{'='*40}")
        lines.append("")
        lines.append("【基本信息】")
        lines.append(f"  当前价格: ${latest['Close']:.2f}")
        lines.append(f"  涨跌幅: {price_change:+.2f}%")
        lines.append(f"  最高价: ${latest['High']:.2f}")
        lines.append(f"  最低价: ${latest['Low']:.2f}")
        lines.append(f"  成交量: {latest['Volume']:,.0f}")
        lines.append(f"  分析日期: {latest.name.strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append("【技术指标】")
        lines.append(f"  MA5: ${latest['MA5']:.2f}  MA10: ${latest['MA10']:.2f}  MA20: ${latest['MA20']:.2f}")
        if pd.notna(latest.get('MA60')):
            lines.append(f"  MA60: ${latest['MA60']:.2f}")
        lines.append(f"  MACD DIF: {latest['MACD_DIF']:.4f}  DEA: {latest['MACD_DEA']:.4f}")
        lines.append(f"  RSI(14): {latest['RSI']:.2f}")
        lines.append(f"  K: {latest['K']:.2f}  D: {latest['D']:.2f}  J: {latest['J']:.2f}")
        lines.append(f"  布林带: 上轨${latest['BB_Upper']:.2f} 中轨${latest['BB_Middle']:.2f} 下轨${latest['BB_Lower']:.2f}")
        lines.append(f"  ATR(14): {latest['ATR']:.4f}")
        lines.append(f"  成交量比率: {latest['Volume_Ratio']:.2f}")
        lines.append("")
        lines.append("【信号分析】")
        for detail in recommendation['details']:
            lines.append(f"  - {detail}")
        lines.append("")
        lines.append("【综合评估】")
        lines.append(f"  多头信号: {recommendation['bullish_signals']}  空头信号: {recommendation['bearish_signals']}")
        lines.append(f"  综合评分: {recommendation['score']:.1f}/100")
        lines.append("")
        lines.append("【投资建议】")
        lines.append(f"  建议操作: {recommendation['recommendation']}")
        lines.append(f"  {recommendation['action_advice']}")
        lines.append("")
        lines.append("【风险提示】")
        lines.append("  本分析仅基于技术指标，不构成投资建议。投资有风险，入市需谨慎。")
        lines.append(f"{'='*40}")

        return "\n".join(lines)

    def run_analysis(self) -> str:
        self.fetch_data()
        self.calculate_all_indicators()
        self.analyze_all()
        return self.generate_report()
