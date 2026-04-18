"""投研周报引擎 - 每周市场概览 + 行业分析 + 个股评分"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.data.yfinance_provider import YFinanceProvider
from app.analysis.stock_analyzer import StockAnalyzer
from app.llm.client import chat

logger = logging.getLogger(__name__)

# ─── 常量定义 ───

INDEX_SYMBOLS = {
    "^GSPC": "S&P 500",
    "^DJI": "道琼斯",
    "^IXIC": "纳斯达克",
}

SECTOR_ETFS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "医疗",
    "XLY": "非必需消费", "XLP": "必需消费", "XLI": "工业",
    "XLB": "材料", "XLRE": "房地产", "XLC": "通信服务", "XLU": "公用事业",
}

# 热门股候选池
HOT_STOCKS = {
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "TSM",
    "JPM", "BAC", "GS", "V", "MA",
    "JNJ", "UNH", "LLY", "ABBV",
    "XOM", "CVX", "COP",
    "WMT", "HD", "NKE", "MCD", "COST",
    "BA", "CAT", "HON",
    "PLTR", "SHOP", "SQ", "COIN",
}

yf_provider = YFinanceProvider()
EXECUTOR = ThreadPoolExecutor(max_workers=5)


# ─── 数据获取 ───

def fetch_index_data() -> list[dict]:
    """获取三大指数本周数据（5日历史 + sparkline）"""
    results = []

    def _fetch_one(symbol: str) -> Optional[dict]:
        try:
            df = yf_provider.get_history(symbol, "5d")
            if df.empty:
                return None
            current = df.iloc[-1]
            prev_close = df.iloc[0]["Open"] if len(df) > 0 else current["Close"]
            sparkline = df["Close"].tolist()
            sparkline_dates = [d.strftime("%m-%d") for d in df.index]
            weekly_change = ((current["Close"] - prev_close) / prev_close) * 100 if prev_close else 0
            return {
                "symbol": symbol,
                "name": INDEX_SYMBOLS.get(symbol, symbol),
                "current": round(current["Close"], 2),
                "weekly_change_pct": round(weekly_change, 2),
                "sparkline": [round(v, 2) for v in sparkline],
                "sparkline_dates": sparkline_dates,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch index {symbol}: {e}")
            return None

    futures = {EXECUTOR.submit(_fetch_one, sym): sym for sym in INDEX_SYMBOLS}
    for future in as_completed(futures):
        result = future.result()
        if result:
            results.append(result)

    results.sort(key=lambda x: x["symbol"])
    return results


def fetch_sector_data() -> list[dict]:
    """获取11个行业ETF的 5日/15日/30日 表现"""
    results = []

    def _fetch_one(symbol: str) -> Optional[dict]:
        try:
            df_30d = yf_provider.get_history(symbol, "1mo")
            if df_30d.empty or len(df_30d) < 5:
                return None

            current = df_30d.iloc[-1]
            current_price = round(current["Close"], 2)

            # 5日（周）
            df_5d = df_30d.tail(5)
            prev_5d = df_5d.iloc[0]["Open"]
            chg_5d = ((current["Close"] - prev_5d) / prev_5d) * 100 if prev_5d else 0

            # 15日（约3周）
            if len(df_30d) >= 15:
                df_15d = df_30d.tail(15)
                prev_15d = df_15d.iloc[0]["Open"]
                chg_15d = ((current["Close"] - prev_15d) / prev_15d) * 100 if prev_15d else 0
            else:
                chg_15d = chg_5d

            # 30日（约1个月）
            prev_30d = df_30d.iloc[0]["Open"]
            chg_30d = ((current["Close"] - prev_30d) / prev_30d) * 100 if prev_30d else 0

            # 成交量
            volume = int(current.get("Volume", 0))
            vol_ma = int(df_30d["Volume"].rolling(20).mean().iloc[-1]) if len(df_30d) >= 20 else volume
            vol_ratio = round(volume / vol_ma, 2) if vol_ma > 0 else 1.0

            return {
                "symbol": symbol,
                "name": SECTOR_ETFS.get(symbol, symbol),
                "current": current_price,
                "weekly_change_pct": round(chg_5d, 2),
                "chg_15d": round(chg_15d, 2),
                "chg_30d": round(chg_30d, 2),
                "volume": volume,
                "vol_ratio": vol_ratio,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch sector {symbol}: {e}")
            return None

    futures = {EXECUTOR.submit(_fetch_one, sym): sym for sym in SECTOR_ETFS}
    for future in as_completed(futures):
        result = future.result()
        if result:
            results.append(result)

    results.sort(key=lambda x: x["weekly_change_pct"], reverse=True)
    return results


# ─── 个股评分 ───

def _extract_tech_info(analyzer: StockAnalyzer) -> dict:
    """从 StockAnalyzer 提取技术指标摘要"""
    signals = analyzer.signals
    tech = {}

    # KDJ
    kdj = signals.get("KDJ", {})
    if kdj:
        latest = analyzer.data.iloc[-1]
        tech["KDJ"] = f"K:{latest['K']:.0f} D:{latest['D']:.0f} J:{latest['J']:.0f}"

    # MACD
    macd = signals.get("MACD", {})
    if macd:
        latest = analyzer.data.iloc[-1]
        tech["MACD"] = f"DIF:{latest['MACD_DIF']:.1f} DEA:{latest['MACD_DEA']:.1f}"

    # RSI
    rsi = signals.get("RSI", {})
    if rsi:
        latest = analyzer.data.iloc[-1]
        tech["RSI"] = f"{latest['RSI']:.1f}"

    # MA Trend
    ma = signals.get("MA", {})
    if ma:
        st = ma.get("short_term", "")
        lt = ma.get("long_term", "")
        if st == "bullish" and lt == "bullish":
            tech["MA Trend"] = "多头排列"
        elif st == "bearish" and lt == "bearish":
            tech["MA Trend"] = "空头排列"
        elif st == "bullish":
            tech["MA Trend"] = "偏多"
        elif st == "bearish":
            tech["MA Trend"] = "偏空"
        else:
            tech["MA Trend"] = "中性"

    return tech


def _build_summary(analyzer: StockAnalyzer) -> str:
    """生成技术面文字总结"""
    rec = analyzer.generate_recommendation()
    details = rec.get("details", [])
    if details:
        return "，".join(details[:3]) + "。"
    return rec.get("action_advice", "")


def score_stocks(symbols: list[str], period: str = "3mo") -> list[dict]:
    """用 StockAnalyzer 对给定股票进行评分，含技术指标"""
    results = []

    def _score_one(symbol: str) -> Optional[dict]:
        try:
            analyzer = StockAnalyzer(symbol, period=period)
            analyzer.fetch_data()
            if analyzer.data.empty:
                return None
            analyzer.calculate_all_indicators()
            analyzer.analyze_all()
            rec = analyzer.generate_recommendation()
            tech = _extract_tech_info(analyzer)
            summary = _build_summary(analyzer)
            quote = yf_provider.get_realtime_quote(symbol)

            return {
                "symbol": symbol,
                "score": round(rec["score"], 1),
                "rating": rec["recommendation"],
                "price": round(quote.price, 2) if quote else None,
                "change_pct": round(quote.change_pct, 2) if quote else None,
                "tech": tech,
                "summary": summary,
            }
        except Exception as e:
            logger.warning(f"Failed to score {symbol}: {e}")
            return None

    futures = {EXECUTOR.submit(_score_one, sym): sym for sym in symbols}
    for future in as_completed(futures):
        result = future.result()
        if result:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def select_hot_stocks(watchlist: list[str], top_n: int = 10) -> list[str]:
    """从 HOT_STOCKS 中排除 watchlist，按动量筛选 top N"""
    excluded = set(s.upper() for s in watchlist)
    candidates = [s for s in HOT_STOCKS if s not in excluded]

    def _momentum(symbol: str) -> Optional[tuple[str, float]]:
        try:
            df = yf_provider.get_history(symbol, "1mo")
            if len(df) < 10:
                return None
            latest = df.iloc[-1]
            prev_20 = df["Close"].rolling(20).mean().iloc[-1]
            vol = int(latest.get("Volume", 0))
            vol_ma = int(df["Volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 1
            price_above_ma = (latest["Close"] - prev_20) / prev_20 if prev_20 > 0 else 0
            vol_ratio = vol / vol_ma if vol_ma > 0 else 1
            momentum_score = price_above_ma * 0.6 + min(vol_ratio - 1, 1) * 0.4
            return (symbol, round(momentum_score, 4))
        except Exception:
            return None

    futures = {EXECUTOR.submit(_momentum, sym): sym for sym in candidates}
    scored = []
    for future in as_completed(futures):
        result = future.result()
        if result:
            scored.append(result)

    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:top_n]]


def get_momentum_label(change_pct: float) -> str:
    """根据周涨跌幅判断动量"""
    if change_pct >= 8:
        return "强势"
    elif change_pct >= 3:
        return "偏强"
    elif change_pct >= 0:
        return "中性"
    else:
        return "偏弱"


# ─── AI 分析 ───

def generate_ai_market_summary(index_data: list[dict]) -> str:
    """调用 LLM 生成大盘综述"""
    if not index_data:
        return "市场数据暂不可用"

    parts = []
    for idx in index_data:
        sparkline_str = ", ".join(str(v) for v in idx["sparkline"][-5:])
        parts.append(
            f"- {idx['name']} ({idx['symbol']}): 当前 {idx['current']}, "
            f"周涨跌幅 {idx['weekly_change_pct']:+.2f}%, 近5日收盘 {sparkline_str}"
        )

    user_prompt = (
        "三大指数本周数据：\n"
        + "\n".join(parts)
        + "\n\n请撰写本周美股大盘综述，200字以内。"
    )

    try:
        return chat(
            user_prompt,
            system_prompt=(
                "你是一位资深美股策略分析师。请根据提供的三大指数本周数据，"
                "撰写一段简洁的中文大盘综述。要求：1)总结本周整体走势 2)分析三大指数表现差异 "
                "3)提及关键点位 4)展望下周可能走势。控制在200字以内。"
            ),
        )
    except Exception as e:
        logger.error(f"AI market summary failed: {e}")
        return "AI 分析暂不可用"


def generate_ai_sector_summary(sector_data: list[dict]) -> str:
    """调用 LLM 生成行业分析"""
    if not sector_data:
        return "行业数据暂不可用"

    parts = []
    for sec in sector_data:
        parts.append(
            f"- {sec['name']} ({sec['symbol']}): 周涨跌 {sec['weekly_change_pct']:+.2f}%, "
            f"15日 {sec['chg_15d']:+.2f}%, 30日 {sec['chg_30d']:+.2f}%, "
            f"当前价 ${sec['current']}"
        )

    user_prompt = (
        "11个行业板块ETF本周表现（按周涨跌幅排序）：\n"
        + "\n".join(parts)
        + "\n\n请分析本周行业轮动趋势并给出配置建议，200字以内。"
    )

    try:
        return chat(
            user_prompt,
            system_prompt=(
                "你是一位行业轮动分析师。请根据提供的行业ETF本周表现数据，分析行业轮动趋势。"
                "要求：1)指出领涨和领跌板块 2)分析市场风格 3)给出下周配置建议。控制在200字以内。"
            ),
        )
    except Exception as e:
        logger.error(f"AI sector summary failed: {e}")
        return "AI 分析暂不可用"


# ─── 周报主入口 ───

def get_report_section_market() -> dict:
    """获取大盘综述 section 数据"""
    try:
        indices = fetch_index_data()
        ai_summary = generate_ai_market_summary(indices) if indices else "市场数据暂不可用"
        return {"indices": indices, "ai_market_summary": ai_summary}
    except Exception as e:
        logger.error(f"Market section error: {e}", exc_info=True)
        return {"indices": [], "ai_market_summary": "数据加载失败"}


def get_report_section_sector() -> dict:
    """获取行业板块 section 数据"""
    try:
        sectors = fetch_sector_data()
        ai_summary = generate_ai_sector_summary(sectors) if sectors else "行业数据暂不可用"
        return {"sectors": sectors, "ai_sector_summary": ai_summary}
    except Exception as e:
        logger.error(f"Sector section error: {e}", exc_info=True)
        return {"sectors": [], "ai_sector_summary": "数据加载失败"}


def get_report_section_stocks(watchlist: Optional[list[str]] = None) -> dict:
    """获取个股评分 section 数据"""
    if watchlist is None:
        watchlist = []
    try:
        # Watchlist scoring
        watchlist_scores = score_stocks(watchlist, period="3mo") if watchlist else []

        # Hot stock selection & scoring
        hot_symbols = select_hot_stocks(watchlist, top_n=10)
        hot_stock_scores = score_stocks(hot_symbols, period="3mo") if hot_symbols else []

        # Add momentum labels to hot stocks
        for stock in hot_stock_scores:
            stock["momentum"] = get_momentum_label(stock.get("change_pct", 0))

        return {
            "watchlist_scores": watchlist_scores,
            "hot_stock_scores": hot_stock_scores,
        }
    except Exception as e:
        logger.error(f"Stocks section error: {e}", exc_info=True)
        return {"watchlist_scores": [], "hot_stock_scores": []}
