import logging
import pandas as pd
from app.llm.client import chat
from app.analysis.stock_analyzer import StockAnalyzer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位经验丰富的美股交易分析师。
你擅长基于技术指标进行量价分析，给出清晰、简洁的交易建议。
回复要求：
- 使用中文
- 简洁有力，控制在 200 字以内
- 明确给出趋势判断和操作建议
- 指出关键支撑位和压力位
- 风险提示"""


async def analyze_with_ai(symbol: str, period: str = "1y") -> tuple[str, str]:
    """
    运行技术分析 + AI 分析

    Returns:
        (technical_report, ai_advice) 技术分析报告和AI建议
    """
    analyzer = StockAnalyzer(symbol, period)
    technical_report = analyzer.run_analysis()

    latest = analyzer.data.iloc[-1]
    prev = analyzer.data.iloc[-2]
    recommendation = analyzer.generate_recommendation()

    sma60_str = f"${latest['SMA_60']:.2f}" if 'SMA_60' in latest.index and pd.notna(latest.get('SMA_60')) else 'N/A'

    prompt = f"""分析美股 {symbol}。

【技术数据摘要】
- 当前价格: ${latest['Close']:.2f} (昨日: ${prev['Close']:.2f})
- 均线: SMA5=${latest['SMA_5']:.2f}, SMA20=${latest['SMA_20']:.2f}, SMA60={sma60_str}
- 动能: RSI={latest['RSI_14']:.2f}, KDJ(K={latest['K_9_3']:.1f}, D={latest['D_9_3']:.1f}, J={latest['J_9_3']:.1f})
- MACD: DIF={latest['MACD_12_26_9']:.4f}, DEA={latest['MACDs_12_26_9']:.4f}
- 布林带: 上轨${latest['BBU_20_2.0_2.0']:.2f}, 中轨${latest['BBM_20_2.0_2.0']:.2f}, 下轨${latest['BBL_20_2.0_2.0']:.2f}
- 成交量比率: {latest['Volume_Ratio']:.2f}
- ATR: {latest['ATRr_14']:.4f}
- 综合评分: {recommendation['score']:.1f}/100 ({recommendation['recommendation']})

【信号要点】
{chr(10).join('- ' + d for d in recommendation['details'])}

请给出你的交易分析和操作建议。"""

    try:
        ai_advice = await chat(prompt, system_prompt=SYSTEM_PROMPT)
    except Exception as e:
        logger.error(f"AI analysis failed for {symbol}: {e}")
        ai_advice = f"AI 分析暂时不可用: {e}"

    return technical_report, ai_advice
