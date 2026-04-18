"""投研周报引擎 - 每周市场概览 + 行业分析 + 个股评分"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.data.yfinance_provider import YFinanceProvider
from app.analysis.stock_analyzer import StockAnalyzer
from app.llm.client import chat, get_model
from db.models import WeeklyReport, ReportConfig

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

# ─── 默认 Prompt 常量 ───

DEFAULT_MARKET_SYSTEM_PROMPT = (
    "你是一位资深美股策略分析师。请根据提供的三大指数本周数据，"
    "撰写一段简洁的中文大盘综述。要求：1)总结本周整体走势 2)分析三大指数表现差异 "
    "3)提及关键点位 4)展望下周可能走势。控制在200字以内。"
)

DEFAULT_SECTOR_SYSTEM_PROMPT = (
    "你是一位行业轮动分析师。请根据提供的行业ETF本周表现数据，分析行业轮动趋势。"
    "要求：1)指出领涨和领跌板块 2)分析市场风格 3)给出下周配置建议。控制在200字以内。"
)

DEFAULT_STOCKS_SYSTEM_PROMPT = ""  # 预留：个股综合分析 prompt

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

async def generate_ai_market_summary(index_data: list[dict], system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成大盘综述"""
    if not index_data:
        return "市场数据暂不可用"

    prompt = system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT

    parts = []
    for idx in index_data:
        sparkline_str = ", ".join(str(v) for v in idx["sparkline"][-5:])
        parts.append(
            f"- {idx['name']} ({idx['symbol']}): 当前 {idx['current']}, "
            f"周涨跌幅 {idx['weekly_change_pct']:+.2f}%, 近5日收盘 {sparkline_str}"
        )

    user_prompt = "三大指数本周数据：\n" + "\n".join(parts)

    try:
        return await chat(user_prompt, system_prompt=prompt)
    except Exception as e:
        logger.error(f"AI market summary failed: {e}")
        return "AI 分析暂不可用"


async def generate_ai_sector_summary(sector_data: list[dict], system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成行业分析"""
    if not sector_data:
        return "行业数据暂不可用"

    prompt = system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT

    parts = []
    for sec in sector_data:
        parts.append(
            f"- {sec['name']} ({sec['symbol']}): 周涨跌 {sec['weekly_change_pct']:+.2f}%, "
            f"15日 {sec['chg_15d']:+.2f}%, 30日 {sec['chg_30d']:+.2f}%, "
            f"当前价 ${sec['current']}"
        )

    user_prompt = "11个行业板块ETF本周表现（按周涨跌幅排序）：\n" + "\n".join(parts)

    try:
        return await chat(user_prompt, system_prompt=prompt)
    except Exception as e:
        logger.error(f"AI sector summary failed: {e}")
        return "AI 分析暂不可用"


# ─── 周报主入口 ───

async def get_report_section_market() -> dict:
    """获取大盘综述 section 数据"""
    try:
        indices = await asyncio.to_thread(fetch_index_data)
        ai_summary = await generate_ai_market_summary(indices) if indices else "市场数据暂不可用"
        return {"indices": indices, "ai_market_summary": ai_summary}
    except Exception as e:
        logger.error(f"Market section error: {e}", exc_info=True)
        return {"indices": [], "ai_market_summary": "数据加载失败"}


async def get_report_section_sector() -> dict:
    """获取行业板块 section 数据"""
    try:
        sectors = await asyncio.to_thread(fetch_sector_data)
        ai_summary = await generate_ai_sector_summary(sectors) if sectors else "行业数据暂不可用"
        return {"sectors": sectors, "ai_sector_summary": ai_summary}
    except Exception as e:
        logger.error(f"Sector section error: {e}", exc_info=True)
        return {"sectors": [], "ai_sector_summary": "数据加载失败"}


async def get_report_section_stocks(watchlist: Optional[list[str]] = None) -> dict:
    """获取个股评分 section 数据"""
    if watchlist is None:
        watchlist = []
    try:
        # Watchlist scoring
        watchlist_scores = await asyncio.to_thread(score_stocks, watchlist, "3mo") if watchlist else []

        # Hot stock selection & scoring
        hot_symbols = await asyncio.to_thread(select_hot_stocks, watchlist, 10)
        hot_stock_scores = await asyncio.to_thread(score_stocks, hot_symbols, "3mo") if hot_symbols else []

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


# ─── DB 辅助函数 ───

def _get_next_version(db: Session) -> int:
    """计算下一个报告版本号"""
    from sqlalchemy import func
    max_ver = db.query(func.max(WeeklyReport.version)).scalar()
    return (max_ver or 0) + 1


def get_or_create_report_config(db: Session) -> ReportConfig:
    """获取或创建 ReportConfig 单例（id=1）"""
    config = db.query(ReportConfig).filter(ReportConfig.id == 1).first()
    if not config:
        config = ReportConfig(
            id=1,
            default_market_system_prompt=DEFAULT_MARKET_SYSTEM_PROMPT,
            default_sector_system_prompt=DEFAULT_SECTOR_SYSTEM_PROMPT,
            default_stocks_system_prompt=DEFAULT_STOCKS_SYSTEM_PROMPT,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _resolve_prompts(config: ReportConfig) -> tuple[str, str, str]:
    """从 ReportConfig 解析 prompt，空值回退到默认常量"""
    market_prompt = config.default_market_system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT
    sector_prompt = config.default_sector_system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT
    stocks_prompt = config.default_stocks_system_prompt or DEFAULT_STOCKS_SYSTEM_PROMPT
    return market_prompt, sector_prompt, stocks_prompt


# ─── 全量报告生成（编排器） ───

async def generate_full_report(
    db: Session,
    trigger: str = "manual",
    watchlist: Optional[list[str]] = None,
) -> dict:
    """
    生成完整周报，写入 DB。

    流程：
    1. 创建 WeeklyReport 行 (status=running)
    2. 并行获取三大模块数据 + AI 分析
    3. 序列化 JSON 写入 DB
    4. 更新 status=completed / failed
    5. 返回 {"report_id": int, "version": int}
    """
    if watchlist is None:
        watchlist = []

    version = _get_next_version(db)
    config = get_or_create_report_config(db)
    market_prompt, sector_prompt, stocks_prompt = _resolve_prompts(config)
    model_name = get_model()

    # 1. 创建 DB 行
    report = WeeklyReport(
        version=version,
        report_date=datetime.now(timezone.utc),
        status="running",
        trigger=trigger,
        model_name=model_name,
        market_system_prompt=market_prompt,
        sector_system_prompt=sector_prompt,
        stocks_system_prompt=stocks_prompt,
        watchlist_used=json.dumps(watchlist),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    try:
        # 2. 并行获取数据 + AI 分析
        index_data, sector_data, stocks_data = await asyncio.gather(
            asyncio.to_thread(fetch_index_data),
            asyncio.to_thread(fetch_sector_data),
            get_report_section_stocks(watchlist),
        )

        # AI 分析（依赖上面的数据）
        ai_market_summary, ai_sector_summary = await asyncio.gather(
            generate_ai_market_summary(index_data, system_prompt=market_prompt),
            generate_ai_sector_summary(sector_data, system_prompt=sector_prompt),
        )

        # 3. 序列化 JSON 并更新 DB
        report.index_data = json.dumps(index_data, ensure_ascii=False)
        report.sector_data = json.dumps(sector_data, ensure_ascii=False)
        report.watchlist_scores = json.dumps(stocks_data.get("watchlist_scores", []), ensure_ascii=False)
        report.hot_stock_scores = json.dumps(stocks_data.get("hot_stock_scores", []), ensure_ascii=False)
        report.ai_market_summary = ai_market_summary
        report.ai_sector_summary = ai_sector_summary
        report.status = "completed"
        db.commit()

        logger.info(f"Report v{version} (id={report_id}) generated successfully")
        return {"report_id": report_id, "version": version}

    except Exception as e:
        logger.error(f"Report v{version} (id={report_id}) generation failed: {e}", exc_info=True)
        report.status = "failed"
        report.error_message = str(e)
        db.commit()
        return {"report_id": report_id, "version": version, "error": str(e)}
