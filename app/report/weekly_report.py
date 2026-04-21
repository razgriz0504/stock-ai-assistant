"""投研周报引擎 - 每周市场概览 + 行业分析 + 个股评分"""
import asyncio
import json
import logging
import pandas as pd
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

# 指数对应的代理 ETF（yfinance 对 ETF 的 info 返回更完整的估值数据）
INDEX_ETF_PROXY = {
    "^GSPC": "SPY",
    "^DJI": "DIA",
    "^IXIC": "QQQ",
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
    "数据格式说明：JSON 数组，每个元素包含 name(指数名), symbol(代码), current(当前点位), "
    "weekly_change_pct(周涨跌幅%), recent_5d_close(近5日收盘列表), "
    "vol_ratios_5d(近5日量比，可选), forward_pe(预测市盈率，可选), trailing_pe(滚动市盈率，可选)。"
)

DEFAULT_SECTOR_SYSTEM_PROMPT = (
    "数据格式说明：JSON 数组，按周涨跌幅排序，每个元素包含 name(行业名), symbol(ETF代码), "
    "weekly_change_pct(周涨跌幅%), chg_15d(15日涨跌幅%), chg_30d(30日涨跌幅%), "
    "current(当前价), vol_ratio(量比)。"
)

DEFAULT_CAPITAL_SYSTEM_PROMPT = ""  # 资金面分析：纯 LLM 联网搜索，无系统注入数据

DEFAULT_GEOPOLITICS_SYSTEM_PROMPT = ""  # 国际局势分析：纯 LLM 联网搜索，无系统注入数据

DEFAULT_STOCKS_SYSTEM_PROMPT = ""  # 预留：个股综合分析 prompt

yf_provider = YFinanceProvider()
EXECUTOR = ThreadPoolExecutor(max_workers=5)


# ─── 数据获取 ───

def fetch_index_data() -> list[dict]:
    """获取三大指数本周数据（5日历史 + 成交量 + 估值）"""
    results = []

    def _fetch_one(symbol: str) -> Optional[dict]:
        try:
            # 5日行情
            df = yf_provider.get_history(symbol, "5d")
            if df.empty:
                return None
            current = df.iloc[-1]
            prev_close = df.iloc[0]["Open"] if len(df) > 0 else current["Close"]
            sparkline = df["Close"].tolist()
            sparkline_dates = [d.strftime("%m-%d") for d in df.index]
            weekly_change = ((current["Close"] - prev_close) / prev_close) * 100 if prev_close else 0

            # 近5日量比（相对20日均量）
            df_vol = yf_provider.get_history(symbol, "1mo")
            vol_ratios = []
            if not df_vol.empty and len(df_vol) >= 5:
                vol_ma20 = df_vol["Volume"].rolling(20).mean()
                for i in range(-5, 0):
                    if i < len(df_vol) and i <= -1:
                        ma = vol_ma20.iloc[i] if not vol_ma20.iloc[i] != vol_ma20.iloc[i] else 1  # NaN check
                        vol = df_vol["Volume"].iloc[i]
                        vol_ratios.append(round(vol / ma, 2) if ma and ma > 0 else 1.0)

            # Forward P/E：优先从指数获取，若为空则从代理 ETF 获取
            pe_info = {}
            try:
                import yfinance as yf
                # 先尝试指数本身
                ticker = yf.Ticker(symbol)
                info = ticker.info
                pe_info["forward_pe"] = info.get("forwardPE")
                pe_info["trailing_pe"] = info.get("trailingPE")
                # 指数无 P/E 数据时，用代理 ETF
                if not pe_info.get("forward_pe") and not pe_info.get("trailing_pe"):
                    etf_symbol = INDEX_ETF_PROXY.get(symbol)
                    if etf_symbol:
                        etf_ticker = yf.Ticker(etf_symbol)
                        etf_info = etf_ticker.info
                        pe_info["forward_pe"] = etf_info.get("forwardPE")
                        pe_info["trailing_pe"] = etf_info.get("trailingPE")
            except Exception:
                pass

            return {
                "symbol": symbol,
                "name": INDEX_SYMBOLS.get(symbol, symbol),
                "current": round(current["Close"], 2),
                "weekly_change_pct": round(weekly_change, 2),
                "sparkline": [round(v, 2) for v in sparkline],
                "sparkline_dates": sparkline_dates,
                "vol_ratios": vol_ratios[-5:] if vol_ratios else [],
                "forward_pe": pe_info.get("forward_pe"),
                "trailing_pe": pe_info.get("trailing_pe"),
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
    tech = {}
    latest = analyzer.data.iloc[-1]

    # KDJ
    if pd.notna(latest.get('K_9_3')):
        tech["KDJ"] = f"K:{latest['K_9_3']:.0f} D:{latest['D_9_3']:.0f} J:{latest['J_9_3']:.0f}"

    # MACD
    if pd.notna(latest.get('MACD_12_26_9')):
        tech["MACD"] = f"DIF:{latest['MACD_12_26_9']:.1f} DEA:{latest['MACDs_12_26_9']:.1f}"

    # RSI
    if pd.notna(latest.get('RSI_14')):
        tech["RSI"] = f"{latest['RSI_14']:.1f}"

    # MA Trend
    short_term = "bullish" if pd.notna(latest.get('SMA_5')) and latest['SMA_5'] > latest['SMA_10'] else "bearish"
    long_term = "neutral"
    if pd.notna(latest.get('SMA_60')):
        long_term = "bullish" if latest['SMA_20'] > latest['SMA_60'] else "bearish"
    if short_term == "bullish" and long_term == "bullish":
        tech["MA Trend"] = "多头排列"
    elif short_term == "bearish" and long_term == "bearish":
        tech["MA Trend"] = "空头排列"
    elif short_term == "bullish":
        tech["MA Trend"] = "偏多"
    elif short_term == "bearish":
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
            rec = analyzer.generate_recommendation()
            tech = _extract_tech_info(analyzer)
            summary = _build_summary(analyzer)
            quote = yf_provider.get_realtime_quote(symbol)

            return {
                "symbol": symbol,
                "score": round(rec["score"], 1),
                "rating": rec["rating"],
                "recommendation": rec["recommendation"],
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
    """调用 LLM 生成大盘综述，user_prompt 只传纯数据，描述由 system_prompt 控制"""
    if not index_data:
        return "市场数据暂不可用"

    prompt = system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT

    # 构建纯数据列表，不加任何描述性文字
    data = []
    for idx in index_data:
        item = {
            "name": idx["name"],
            "symbol": idx["symbol"],
            "current": idx["current"],
            "weekly_change_pct": idx["weekly_change_pct"],
            "recent_5d_close": idx["sparkline"][-5:],
        }
        # 成交量数据（近5日量比）
        if idx.get("vol_ratios"):
            item["vol_ratios_5d"] = idx["vol_ratios"]
        # 估值数据（始终传入，null 表示系统未获取到，LLM 应联网搜索）
        item["forward_pe"] = idx.get("forward_pe")
        item["trailing_pe"] = idx.get("trailing_pe")
        data.append(item)

    user_prompt = json.dumps(data, ensure_ascii=False)

    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=True)
    except Exception as e:
        logger.error(f"AI market summary failed: {e}")
        return "AI 分析暂不可用"


async def generate_ai_sector_summary(sector_data: list[dict], system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成行业分析，user_prompt 只传纯数据，描述由 system_prompt 控制"""
    if not sector_data:
        return "行业数据暂不可用"

    prompt = system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT

    # 构建纯数据列表，不加任何描述性文字
    data = []
    for sec in sector_data:
        data.append({
            "name": sec["name"],
            "symbol": sec["symbol"],
            "weekly_change_pct": sec["weekly_change_pct"],
            "chg_15d": sec["chg_15d"],
            "chg_30d": sec["chg_30d"],
            "current": sec["current"],
            "vol_ratio": sec.get("vol_ratio", 1.0),
        })

    user_prompt = json.dumps(data, ensure_ascii=False)

    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=True)
    except Exception as e:
        logger.error(f"AI sector summary failed: {e}")
        return "AI 分析暂不可用"


async def generate_ai_capital_summary(system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成资金面分析，纯联网搜索无系统数据注入"""
    prompt = system_prompt or DEFAULT_CAPITAL_SYSTEM_PROMPT
    user_prompt = "请分析本周美股资金面情况，包括美联储政策动向、国债收益率变化、市场流动性指标、资金流向等。"
    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=True)
    except Exception as e:
        logger.error(f"AI capital summary failed: {e}")
        return "AI 分析暂不可用"


async def generate_ai_geopolitics_summary(system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成国际局势分析，纯联网搜索无系统数据注入"""
    prompt = system_prompt or DEFAULT_GEOPOLITICS_SYSTEM_PROMPT
    user_prompt = "请分析本周影响美股市场的国际局势因素，包括地缘政治动态、贸易政策变化、主要经济体宏观政策、国际冲突与外交进展等。"
    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=True)
    except Exception as e:
        logger.error(f"AI geopolitics summary failed: {e}")
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


async def get_report_section_capital(system_prompt: Optional[str] = None) -> dict:
    """获取资金面分析 section 数据（纯 LLM 输出）"""
    try:
        ai_summary = await generate_ai_capital_summary(system_prompt=system_prompt)
        return {"ai_capital_summary": ai_summary}
    except Exception as e:
        logger.error(f"Capital section error: {e}", exc_info=True)
        return {"ai_capital_summary": "数据加载失败"}


async def get_report_section_geopolitics(system_prompt: Optional[str] = None) -> dict:
    """获取国际局势分析 section 数据（纯 LLM 输出）"""
    try:
        ai_summary = await generate_ai_geopolitics_summary(system_prompt=system_prompt)
        return {"ai_geopolitics_summary": ai_summary}
    except Exception as e:
        logger.error(f"Geopolitics section error: {e}", exc_info=True)
        return {"ai_geopolitics_summary": "数据加载失败"}


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
            default_capital_system_prompt=DEFAULT_CAPITAL_SYSTEM_PROMPT,
            default_geopolitics_system_prompt=DEFAULT_GEOPOLITICS_SYSTEM_PROMPT,
            default_sector_system_prompt=DEFAULT_SECTOR_SYSTEM_PROMPT,
            default_stocks_system_prompt=DEFAULT_STOCKS_SYSTEM_PROMPT,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _resolve_prompts(config: ReportConfig) -> tuple[str, str, str, str, str]:
    """从 ReportConfig 解析 prompt，空值回退到默认常量"""
    market_prompt = config.default_market_system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT
    capital_prompt = config.default_capital_system_prompt or DEFAULT_CAPITAL_SYSTEM_PROMPT
    geopolitics_prompt = config.default_geopolitics_system_prompt or DEFAULT_GEOPOLITICS_SYSTEM_PROMPT
    sector_prompt = config.default_sector_system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT
    stocks_prompt = config.default_stocks_system_prompt or DEFAULT_STOCKS_SYSTEM_PROMPT
    return market_prompt, capital_prompt, geopolitics_prompt, sector_prompt, stocks_prompt


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
    market_prompt, capital_prompt, geopolitics_prompt, sector_prompt, stocks_prompt = _resolve_prompts(config)
    model_name = get_model()

    # 1. 创建 DB 行
    report = WeeklyReport(
        version=version,
        report_date=datetime.now(timezone.utc),
        status="running",
        trigger=trigger,
        model_name=model_name,
        market_system_prompt=market_prompt,
        capital_system_prompt=capital_prompt,
        geopolitics_system_prompt=geopolitics_prompt,
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

        # AI 分析（依赖上面的数据 + 纯 LLM 模块）
        ai_market_summary, ai_capital_summary, ai_geopolitics_summary, ai_sector_summary = await asyncio.gather(
            generate_ai_market_summary(index_data, system_prompt=market_prompt),
            generate_ai_capital_summary(system_prompt=capital_prompt),
            generate_ai_geopolitics_summary(system_prompt=geopolitics_prompt),
            generate_ai_sector_summary(sector_data, system_prompt=sector_prompt),
        )

        # 3. 序列化 JSON 并更新 DB
        report.index_data = json.dumps(index_data, ensure_ascii=False)
        report.sector_data = json.dumps(sector_data, ensure_ascii=False)
        report.watchlist_scores = json.dumps(stocks_data.get("watchlist_scores", []), ensure_ascii=False)
        report.hot_stock_scores = json.dumps(stocks_data.get("hot_stock_scores", []), ensure_ascii=False)
        report.ai_market_summary = ai_market_summary
        report.ai_capital_summary = ai_capital_summary
        report.ai_geopolitics_summary = ai_geopolitics_summary
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
