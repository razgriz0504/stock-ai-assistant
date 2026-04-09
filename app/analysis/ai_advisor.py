import logging
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

    prompt = f"""分析美股 {symbol}。

【技术数据摘要】
- 当前价格: ${latest['Close']:.2f} (昨日: ${prev['Close']:.2f})
- 均线: MA5=${latest['MA5']:.2f}, MA20=${latest['MA20']:.2f}, MA60={f"${latest['MA60']:.2f}" if 'MA60' in latest and not __import__('pandas').isna(latest.get('MA60')) else 'N/A'}
- 动能: RSI={latest['RSI']:.2f}, KDJ(K={latest['K']:.1f}, D={latest['D']:.1f}, J={latest['J']:.1f})
- MACD: DIF={latest['MACD_DIF']:.4f}, DEA={latest['MACD_DEA']:.4f}
- 布林带: 上轨${latest['BB_Upper']:.2f}, 中轨${latest['BB_Middle']:.2f}, 下轨${latest['BB_Lower']:.2f}
- 成交量比率: {latest['Volume_Ratio']:.2f}
- ATR: {latest['ATR']:.4f}
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
