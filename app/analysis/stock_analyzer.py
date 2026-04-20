"""
美股股票量价趋势分析器
使用 pandas_ta 计算技术指标，适配服务端调用
"""

import pandas as pd
import pandas_ta as ta
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
        self.stock_name = self.symbol

    def fetch_data(self) -> pd.DataFrame:
        self.data = _yf_provider.get_history(self.symbol, self.period)
        if self.data.empty:
            raise ValueError(f"无法获取 {self.symbol} 的数据，请检查股票代码是否正确")
        return self.data

    # ==================== 技术指标计算 ====================

    def calculate_all_indicators(self):
        """使用 pandas_ta 计算全部技术指标"""
        # SMA
        for length in [5, 10, 20, 60, 120]:
            self.data.ta.sma(length=length, append=True)
        # EMA
        self.data.ta.ema(length=12, append=True)
        self.data.ta.ema(length=26, append=True)
        # MACD
        self.data.ta.macd(fast=12, slow=26, signal=9, append=True)
        # RSI
        self.data.ta.rsi(length=14, append=True)
        # KDJ
        self.data.ta.kdj(length=9, signal=3, append=True)
        # 布林带
        self.data.ta.bbands(length=20, std=2, append=True)
        # ATR
        self.data.ta.atr(length=14, append=True)
        # OBV
        self.data.ta.obv(append=True)
        # VWAP
        self.data.ta.vwap(append=True)
        # 成交量均线 (pandas_ta SMA 默认用 Close，需手动指定 Volume)
        self.data['Vol_SMA_5'] = ta.sma(self.data['Volume'], length=5)
        self.data['Vol_SMA_20'] = ta.sma(self.data['Volume'], length=20)
        self.data['Volume_Ratio'] = self.data['Volume'] / self.data['Vol_SMA_20']

    # ==================== 投资建议生成 ====================

    def generate_recommendation(self) -> dict:
        score, details = calculate_score(self.data)

        # 将 1-5 分映射到 0-100 分 (保持调用方兼容)
        score_100 = (score - 1) / 4 * 100

        if score >= 4.0:
            recommendation = "买入"
            action_advice = "趋势、动能、量价多项指标共振看多，可以考虑逢低买入或加仓"
        elif score >= 3.5:
            recommendation = "谨慎看多"
            action_advice = "技术面偏多但信号不够强烈，建议轻仓参与或持有观望"
        elif score >= 2.5:
            recommendation = "观望"
            action_advice = "多空信号交织，建议等待更明确的方向信号"
        elif score >= 2.0:
            recommendation = "谨慎看空"
            action_advice = "技术面偏空，建议减仓或暂不介入"
        else:
            recommendation = "卖出"
            action_advice = "趋势、动能指标显示空头主导，建议减仓或止损"

        bullish = sum(1 for d in details if '多头' in d or '扩张' in d or '强势' in d or '放量确认' in d or '向上' in d)
        bearish = sum(1 for d in details if '空头' in d or '超跌' in d)

        return {
            'score': score_100,
            'score_raw': score,
            'recommendation': recommendation,
            'action_advice': action_advice,
            'bullish_signals': bullish,
            'bearish_signals': bearish,
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
        lines.append(f"  SMA5: ${latest['SMA_5']:.2f}  SMA10: ${latest['SMA_10']:.2f}  SMA20: ${latest['SMA_20']:.2f}")
        if 'SMA_60' in latest.index and pd.notna(latest.get('SMA_60')):
            lines.append(f"  SMA60: ${latest['SMA_60']:.2f}")
        lines.append(f"  MACD: {latest['MACD_12_26_9']:.4f}  Signal: {latest['MACDs_12_26_9']:.4f}")
        lines.append(f"  RSI(14): {latest['RSI_14']:.2f}")
        lines.append(f"  K: {latest['K_9_3']:.2f}  D: {latest['D_9_3']:.2f}  J: {latest['J_9_3']:.2f}")
        lines.append(f"  布林带: 上轨${latest['BBU_20_2.0_2.0']:.2f} 中轨${latest['BBM_20_2.0_2.0']:.2f} 下轨${latest['BBL_20_2.0_2.0']:.2f}")
        lines.append(f"  ATR(14): {latest['ATRr_14']:.4f}")
        lines.append(f"  成交量比率: {latest['Volume_Ratio']:.2f}")
        lines.append("")
        lines.append("【信号分析】")
        for detail in recommendation['details']:
            lines.append(f"  - {detail}")
        lines.append("")
        lines.append("【综合评估】")
        lines.append(f"  多头信号: {recommendation['bullish_signals']}  空头信号: {recommendation['bearish_signals']}")
        lines.append(f"  综合评分: {recommendation['score']:.1f}/100 (原始分: {recommendation['score_raw']:.1f}/5)")
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
        return self.generate_report()


def calculate_score(ticker_data):
    """基于趋势/动能/KDJ/量价的综合评分 (1-5 分)"""
    df = ticker_data.copy()
    # 1. 计算核心指标
    # 趋势指标：EMA20, EMA50
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    # 动能指标：MACD
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    # 强度指标：KDJ
    df.ta.kdj(length=9, signal=3, append=True)
    # 量能指标：成交量比率
    df['vol_ma20'] = ta.sma(df['Volume'], length=20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    score = 3.0  # 基准分
    details = []

    # --- 逻辑 A: 趋势得分 (权重 40%) ---
    # 多头排列判定
    if curr['Close'] > curr['EMA_20'] > curr['EMA_50']:
        score += 1.0
        details.append("多头排列：价格 > EMA20 > EMA50")
        if curr['EMA_20'] > prev['EMA_20']:
            score += 0.5  # 斜率向上
            details.append("EMA20 斜率向上，趋势加强")
    elif curr['Close'] < curr['EMA_20'] < curr['EMA_50']:
        score -= 1.5  # 极度空头
        details.append("空头排列：价格 < EMA20 < EMA50")

    # --- 逻辑 B: MACD 动能确认 (权重 30%) ---
    macd_val = curr['MACD_12_26_9']
    macd_hist = curr['MACDh_12_26_9']
    if macd_val > 0 and macd_hist > 0:  # 0轴上多头放量
        score += 0.5
        details.append("MACD 零轴上方多头放量")
    if macd_hist > prev['MACDh_12_26_9']:  # 动能柱扩张
        score += 0.5
        details.append("MACD 动能柱扩张")
    if macd_val < 0 and macd_hist < 0:  # 空头主导
        score -= 1.0
        details.append("MACD 空头主导")

    # --- 逻辑 C: KDJ 状态 (权重 20%) ---
    j_val = curr['J_9_3']
    if j_val > 80:  # 强势区/钝化
        score += 0.5
        details.append(f"KDJ J值={j_val:.1f}，强势区")
    elif j_val < 20:  # 超跌区
        score -= 0.5
        details.append(f"KDJ J值={j_val:.1f}，超跌区")

    # --- 逻辑 D: 量价突破 (权重 10%) ---
    if curr['Volume'] > curr['vol_ma20'] * 1.5 and curr['Close'] > prev['Close']:
        score += 0.5  # 放量确认
        details.append("放量确认：成交量超过 MA20 的 1.5 倍")

    final_score = min(max(score, 1.0), 5.0)  # 限制在 1-5 分
    return final_score, details
