"""投研周报引擎 - 每周市场概览 + 行业分析 + 个股评分"""
import asyncio
import json
import logging
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.data.yfinance_provider import YFinanceProvider
from app.analysis.stock_analyzer import StockAnalyzer
from app.llm.client import chat, get_model
from db.models import WeeklyReport, ReportConfig, XAccount, XTweet

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

DEFAULT_YIELD_CURVE_SYSTEM_PROMPT = (
    "你是一名宏观跨资产策略师，请基于系统提供的美国国债收益率曲线数据，结合\"牛熊×陡平\"四象限框架"
    "（Bear Steepener / Bear Flattener / Bull Steepener / Bull Flattener），给出本周收益率曲线的整体研判与跨资产推论。\n\n"
    "## 数据格式说明\n"
    "JSON 对象包含以下字段：\n"
    "- yields: 当前各期限收益率 {3M, 2Y, 5Y, 10Y, 30Y}（百分比）\n"
    "- weekly_changes_bp: 本周各期限收益率变化（基点）\n"
    "- spreads: 关键利差 {2s10s, 3m10s, 10s30s}（基点）\n"
    "- spread_changes_bp: 利差本周变化（基点）\n"
    "- regime: 系统初判的曲线形态（Bear/Bull × Steepener/Flattener 之一，或 Mixed）\n"
    "- regime_logic: 形态判定依据\n"
    "- cross_asset: 跨资产标的本周表现 {VIX, DXY(美元指数), GLD(黄金), CL=F(原油), SPY}\n\n"
    "## 输出要求\n"
    "请按以下结构输出 Markdown 报告（不超过 800 字）：\n"
    "1. **本周曲线快照**：核心收益率与利差变化的事实性总结\n"
    "2. **形态研判**：确认或修正系统初判，简述驱动逻辑（增长预期 / 通胀预期 / 政策预期 / 避险）\n"
    "3. **跨资产佐证**：用 VIX / 美元 / 黄金 / 油价 / 股指的实际走势验证形态\n"
    "4. **股票市场含义**：本形态对成长股、价值股、银行股、地产、公用事业的相对影响\n"
    "5. **下周关注**：联网搜索本周公布或下周即将公布的关键数据（CPI/PCE/非农/FOMC/拍卖等），点出曲线变盘风险\n\n"
    "请保持客观，不下定向交易指令；如系统数据与联网信息冲突，以联网最新信息为准并标注。"
)

DEFAULT_X_MONITOR_SYSTEM_PROMPT = (
    "你是一名资深的市场情绪分析师。基于系统提供的过去 7 天 X (Twitter) 关键账号推文数据，"
    "撰写一份本周\"舆情综述\"作为周报的一节。\n\n"
    "## 数据格式说明\n"
    "JSON 对象包含：\n"
    "- accounts: 各账号本周的推文摘要列表，每个含 username/display_name/category/tweet_count/sentiment_score/recent_tweets\n"
    "- total_count: 本周推文总数\n"
    "- sentiment_distribution: {bullish, bearish, neutral} 推文条数\n"
    "- top_assets_mentioned: 本周被提及最多的标的及频次\n"
    "- top_tweets: 本周影响最显著的 5-10 条代表性推文（含中文翻译/影响标的/市场影响评述）\n\n"
    "## 输出要求（Markdown，不超过 800 字）：\n"
    "1. **整体舆情温度**：用 1-2 句概括 bullish/bearish/neutral 的整体走向\n"
    "2. **关键议题**：归纳本周最受讨论的 3-5 个议题（如美联储政策、科技股、地缘风险）\n"
    "3. **代表性发言**：选 3-5 条最具影响力的推文，引用账号 + 中译 + 简评\n"
    "4. **被关注标的**：列出本周被提及最多的 ticker 及方向倾向\n"
    "5. **风险提示**：识别本周值得警惕的舆情信号（如官员鹰派表态、CEO 利空言论）\n\n"
    "请客观陈述，不下定向交易建议；区分官方账号（央行/美联储）与个人观点（分析师/CEO）。"
)

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


# ─── 国债收益率曲线 ───

# Yahoo Finance 国债收益率符号
YIELD_SYMBOLS = {
    "3M": "^IRX",   # 13 Week Treasury Bill
    "2Y":  "2YY=F",  # 2-Year Treasury Yield Future（^UST2Y 不稳定，期货代理）
    "5Y":  "^FVX",  # 5-Year Treasury
    "10Y": "^TNX",  # 10-Year Treasury
    "30Y": "^TYX",  # 30-Year Treasury
}

# 跨资产佐证标的
CROSS_ASSET_SYMBOLS = {
    "VIX": "^VIX",
    "DXY": "DX-Y.NYB",
    "GLD": "GLD",
    "CL=F": "CL=F",
    "SPY": "SPY",
}


def _yf_chart_fetch(symbol: str, range_: str = "1mo", interval: str = "1d") -> Optional[dict]:
    """直接调用 Yahoo Finance chart API，绕过 yfinance 限频"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return None
        item = result[0]
        meta = item.get("meta", {})
        closes = item.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        # 过滤 None
        closes = [c for c in closes if c is not None]
        if not closes:
            return None
        return {
            "symbol": symbol,
            "current": meta.get("regularMarketPrice", closes[-1]),
            "closes": closes,
        }
    except Exception as e:
        logger.warning(f"YF chart fetch failed for {symbol}: {e}")
        return None


def _determine_curve_regime(weekly_changes_bp: dict, spread_changes_bp: dict) -> tuple[str, str]:
    """
    根据本周收益率变化与利差变化，判定 4 象限形态。

    四象限框架：
    - Bear Steepener: 长端涨幅 > 短端，10s30s 走阔（增长/通胀预期上行）
    - Bear Flattener: 短端涨幅 > 长端，2s10s 收窄（紧缩预期）
    - Bull Steepener: 短端跌幅 > 长端，2s10s 走阔（降息预期升温）
    - Bull Flattener: 长端跌幅 > 短端，10s30s 收窄（避险/通缩担忧）

    返回 (regime, logic) 二元组。
    """
    short_chg = weekly_changes_bp.get("2Y", 0) or 0
    long_chg = weekly_changes_bp.get("10Y", 0) or 0
    spread_2s10s = spread_changes_bp.get("2s10s", 0) or 0

    # 主轴方向：以 10Y 为代表判断 Bull/Bear
    if abs(short_chg) < 1 and abs(long_chg) < 1:
        return "Mixed", "本周收益率变化幅度有限（<1bp），形态不明确"

    if long_chg > 0 and short_chg > 0:
        # 双边上行 - Bear
        if spread_2s10s > 0:
            return "Bear Steepener", f"长短端齐升，10Y +{long_chg:.1f}bp / 2Y +{short_chg:.1f}bp，2s10s 走阔 {spread_2s10s:+.1f}bp，对应增长/通胀预期上行"
        else:
            return "Bear Flattener", f"长短端齐升，10Y +{long_chg:.1f}bp / 2Y +{short_chg:.1f}bp，2s10s 收窄 {spread_2s10s:+.1f}bp，对应紧缩/前置加息预期"
    elif long_chg < 0 and short_chg < 0:
        # 双边下行 - Bull
        if spread_2s10s > 0:
            return "Bull Steepener", f"长短端齐落，10Y {long_chg:+.1f}bp / 2Y {short_chg:+.1f}bp，2s10s 走阔 {spread_2s10s:+.1f}bp，对应降息预期升温"
        else:
            return "Bull Flattener", f"长短端齐落，10Y {long_chg:+.1f}bp / 2Y {short_chg:+.1f}bp，2s10s 收窄 {spread_2s10s:+.1f}bp，对应避险买长端 / 通缩担忧"
    elif long_chg > 0 and short_chg < 0:
        # 短端跌长端涨 - 强 Bear Steepener / 复苏交易
        return "Bear Steepener", f"短端下行 ({short_chg:+.1f}bp) 长端上行 ({long_chg:+.1f}bp)，强势陡峭化，典型再通胀/复苏交易"
    elif long_chg < 0 and short_chg > 0:
        # 短端涨长端跌 - 强 Bear Flattener / 衰退交易
        return "Bear Flattener", f"短端上行 ({short_chg:+.1f}bp) 长端下行 ({long_chg:+.1f}bp)，曲线倒挂加深，典型衰退交易信号"
    else:
        return "Mixed", f"长短端方向混合：10Y {long_chg:+.1f}bp / 2Y {short_chg:+.1f}bp"


def fetch_yield_curve_data() -> dict:
    """获取国债收益率曲线 + 跨资产数据，并判定形态"""
    yields_now = {}
    yields_prev = {}

    for tenor, symbol in YIELD_SYMBOLS.items():
        data = _yf_chart_fetch(symbol, range_="1mo", interval="1d")
        if not data:
            continue
        closes = data["closes"]
        current = data["current"]
        # ^IRX/TNX/TYX 等已经以百分比报价（如 4.55 = 4.55%）
        # 2YY=F 期货也是 yield 单位
        yields_now[tenor] = round(float(current), 3)
        # 7 个交易日前 ≈ 一周前
        prev_idx = max(-8, -len(closes))
        if abs(prev_idx) <= len(closes):
            yields_prev[tenor] = round(float(closes[prev_idx]), 3)

    # 计算变化（基点 = 百分比 * 100）
    weekly_changes_bp = {}
    for tenor in yields_now:
        if tenor in yields_prev:
            weekly_changes_bp[tenor] = round((yields_now[tenor] - yields_prev[tenor]) * 100, 2)

    # 关键利差（基点）
    def _spread_bp(a: str, b: str) -> Optional[float]:
        if a in yields_now and b in yields_now:
            return round((yields_now[a] - yields_now[b]) * 100, 1)
        return None

    spreads = {
        "2s10s": _spread_bp("10Y", "2Y"),
        "3m10s": _spread_bp("10Y", "3M"),
        "10s30s": _spread_bp("30Y", "10Y"),
    }

    def _spread_chg(a: str, b: str) -> Optional[float]:
        if a in weekly_changes_bp and b in weekly_changes_bp:
            return round(weekly_changes_bp[a] - weekly_changes_bp[b], 2)
        return None

    spread_changes_bp = {
        "2s10s": _spread_chg("10Y", "2Y"),
        "3m10s": _spread_chg("10Y", "3M"),
        "10s30s": _spread_chg("30Y", "10Y"),
    }

    # 形态判定
    regime, regime_logic = _determine_curve_regime(weekly_changes_bp, spread_changes_bp)

    # 跨资产
    cross_asset = {}
    for name, symbol in CROSS_ASSET_SYMBOLS.items():
        data = _yf_chart_fetch(symbol, range_="1mo", interval="1d")
        if not data:
            continue
        closes = data["closes"]
        current = data["current"]
        prev_idx = max(-8, -len(closes))
        prev = closes[prev_idx] if abs(prev_idx) <= len(closes) else closes[0]
        chg_pct = ((current - prev) / prev) * 100 if prev else 0
        cross_asset[name] = {
            "current": round(float(current), 2),
            "weekly_change_pct": round(chg_pct, 2),
        }

    return {
        "yields": yields_now,
        "yields_prev": yields_prev,
        "weekly_changes_bp": weekly_changes_bp,
        "spreads": spreads,
        "spread_changes_bp": spread_changes_bp,
        "regime": regime,
        "regime_logic": regime_logic,
        "cross_asset": cross_asset,
    }


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


async def generate_ai_yield_curve_summary(curve_data: dict, system_prompt: Optional[str] = None) -> str:
    """调用 LLM 生成国债收益率曲线分析，结合系统数据 + 联网搜索"""
    if not curve_data or not curve_data.get("yields"):
        return "国债收益率数据暂不可用"

    prompt = system_prompt or DEFAULT_YIELD_CURVE_SYSTEM_PROMPT
    user_prompt = json.dumps(curve_data, ensure_ascii=False)
    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=True)
    except Exception as e:
        logger.error(f"AI yield curve summary failed: {e}")
        return "AI 分析暂不可用"


# ─── X 舆情监控 数据聚合 ───

def fetch_x_tweets_data(db: Session, days: int = 7) -> dict:
    """聚合最近 N 天已处理的 X 推文，按账号分组并统计情绪/被提及标的。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(XTweet, XAccount)
        .join(XAccount, XTweet.account_id == XAccount.id)
        .filter(XTweet.processed == True)  # noqa: E712
        .filter(XTweet.created_at_x >= cutoff)
        .order_by(XTweet.created_at_x.desc())
        .all()
    )

    if not rows:
        return {
            "accounts": [],
            "total_count": 0,
            "sentiment_distribution": {"bullish": 0, "bearish": 0, "neutral": 0},
            "top_assets_mentioned": [],
            "top_tweets": [],
            "window_days": days,
        }

    sentiment_dist = {"bullish": 0, "bearish": 0, "neutral": 0}
    asset_counter: dict[str, int] = {}
    by_account: dict[int, dict] = {}
    flat_tweets: list[dict] = []

    for tweet, account in rows:
        sent = (tweet.sentiment or "neutral").lower()
        if sent not in sentiment_dist:
            sent = "neutral"
        sentiment_dist[sent] += 1

        try:
            impact_assets = json.loads(tweet.impact_assets) if tweet.impact_assets else []
        except Exception:
            impact_assets = []
        if not isinstance(impact_assets, list):
            impact_assets = []
        for asset in impact_assets:
            if not asset:
                continue
            key = str(asset).upper().strip()
            if key:
                asset_counter[key] = asset_counter.get(key, 0) + 1

        try:
            key_points = json.loads(tweet.key_points) if tweet.key_points else []
        except Exception:
            key_points = []
        if not isinstance(key_points, list):
            key_points = []

        try:
            metrics = json.loads(tweet.metrics) if tweet.metrics else {}
        except Exception:
            metrics = {}
        if not isinstance(metrics, dict):
            metrics = {}
        like_count = int(metrics.get("like_count", 0) or 0)
        retweet_count = int(metrics.get("retweet_count", 0) or 0)

        bucket = by_account.setdefault(
            account.id,
            {
                "username": account.username,
                "display_name": account.display_name or account.username,
                "category": account.category or "",
                "tweet_count": 0,
                "sentiment_counts": {"bullish": 0, "bearish": 0, "neutral": 0},
                "recent_tweets": [],
            },
        )
        bucket["tweet_count"] += 1
        bucket["sentiment_counts"][sent] += 1

        tweet_record = {
            "tweet_id": tweet.tweet_id,
            "created_at": tweet.created_at_x.isoformat() if tweet.created_at_x else None,
            "text": tweet.text or "",
            "text_zh": tweet.text_zh or "",
            "sentiment": sent,
            "impact_assets": impact_assets,
            "market_impact": tweet.market_impact or "",
            "key_points": key_points,
            "like_count": like_count,
            "retweet_count": retweet_count,
        }
        if len(bucket["recent_tweets"]) < 5:
            bucket["recent_tweets"].append(tweet_record)

        flat_tweets.append({**tweet_record, "username": account.username})

    accounts_out = []
    for bucket in by_account.values():
        sc = bucket["sentiment_counts"]
        total = bucket["tweet_count"]
        score = (sc["bullish"] - sc["bearish"]) / total if total else 0.0
        accounts_out.append(
            {
                "username": bucket["username"],
                "display_name": bucket["display_name"],
                "category": bucket["category"],
                "tweet_count": total,
                "sentiment_score": round(score, 3),
                "sentiment_counts": sc,
                "recent_tweets": bucket["recent_tweets"],
            }
        )
    accounts_out.sort(key=lambda x: x["tweet_count"], reverse=True)

    top_assets = sorted(asset_counter.items(), key=lambda kv: kv[1], reverse=True)[:15]
    top_assets_out = [{"ticker": k, "count": v} for k, v in top_assets]

    flat_tweets.sort(
        key=lambda t: (t.get("like_count", 0) + t.get("retweet_count", 0)),
        reverse=True,
    )
    top_tweets_out = flat_tweets[:10]

    return {
        "accounts": accounts_out,
        "total_count": len(flat_tweets),
        "sentiment_distribution": sentiment_dist,
        "top_assets_mentioned": top_assets_out,
        "top_tweets": top_tweets_out,
        "window_days": days,
    }


async def generate_ai_x_monitor_summary(
    x_data: dict, system_prompt: Optional[str] = None
) -> str:
    """调用 LLM 生成 X 舆情综述"""
    if not x_data or x_data.get("total_count", 0) == 0:
        return "本周暂无 X 关键账号推文数据"

    prompt = system_prompt or DEFAULT_X_MONITOR_SYSTEM_PROMPT
    user_prompt = json.dumps(x_data, ensure_ascii=False)
    try:
        return await chat(user_prompt, system_prompt=prompt, web_search=False)
    except Exception as e:
        logger.error(f"AI X monitor summary failed: {e}")
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


async def get_report_section_yield_curve(system_prompt: Optional[str] = None) -> dict:
    """获取国债收益率曲线 section 数据"""
    try:
        curve_data = await asyncio.to_thread(fetch_yield_curve_data)
        ai_summary = await generate_ai_yield_curve_summary(curve_data, system_prompt=system_prompt) if curve_data else "数据暂不可用"
        return {"yield_curve": curve_data, "ai_yield_curve_summary": ai_summary}
    except Exception as e:
        logger.error(f"Yield curve section error: {e}", exc_info=True)
        return {"yield_curve": {}, "ai_yield_curve_summary": "数据加载失败"}


async def get_report_section_x_monitor(db: Session, system_prompt: Optional[str] = None, days: int = 7) -> dict:
    """获取 X 舆情监控 section 数据"""
    try:
        x_data = await asyncio.to_thread(fetch_x_tweets_data, db, days)
        ai_summary = await generate_ai_x_monitor_summary(x_data, system_prompt=system_prompt)
        return {"x_tweets_data": x_data, "ai_x_monitor_summary": ai_summary}
    except Exception as e:
        logger.error(f"X monitor section error: {e}", exc_info=True)
        return {"x_tweets_data": {}, "ai_x_monitor_summary": "数据加载失败"}


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
        from app.x_monitor.processor import DEFAULT_X_TWEET_SYSTEM_PROMPT
        config = ReportConfig(
            id=1,
            default_market_system_prompt=DEFAULT_MARKET_SYSTEM_PROMPT,
            default_capital_system_prompt=DEFAULT_CAPITAL_SYSTEM_PROMPT,
            default_geopolitics_system_prompt=DEFAULT_GEOPOLITICS_SYSTEM_PROMPT,
            default_sector_system_prompt=DEFAULT_SECTOR_SYSTEM_PROMPT,
            default_stocks_system_prompt=DEFAULT_STOCKS_SYSTEM_PROMPT,
            default_yield_curve_system_prompt=DEFAULT_YIELD_CURVE_SYSTEM_PROMPT,
            default_x_tweet_system_prompt=DEFAULT_X_TWEET_SYSTEM_PROMPT,
            default_x_monitor_system_prompt=DEFAULT_X_MONITOR_SYSTEM_PROMPT,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _resolve_prompts(config: ReportConfig) -> tuple[str, str, str, str, str, str, str]:
    """从 ReportConfig 解析 prompt，空值回退到默认常量。返回 7-tuple。"""
    market_prompt = config.default_market_system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT
    capital_prompt = config.default_capital_system_prompt or DEFAULT_CAPITAL_SYSTEM_PROMPT
    geopolitics_prompt = config.default_geopolitics_system_prompt or DEFAULT_GEOPOLITICS_SYSTEM_PROMPT
    sector_prompt = config.default_sector_system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT
    stocks_prompt = config.default_stocks_system_prompt or DEFAULT_STOCKS_SYSTEM_PROMPT
    yield_curve_prompt = (
        getattr(config, "default_yield_curve_system_prompt", None)
        or DEFAULT_YIELD_CURVE_SYSTEM_PROMPT
    )
    x_monitor_prompt = (
        getattr(config, "default_x_monitor_system_prompt", None)
        or DEFAULT_X_MONITOR_SYSTEM_PROMPT
    )
    return (
        market_prompt,
        capital_prompt,
        geopolitics_prompt,
        sector_prompt,
        stocks_prompt,
        yield_curve_prompt,
        x_monitor_prompt,
    )


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
    2. 并行获取数据模块 + AI 分析
    3. 序列化 JSON 写入 DB
    4. 更新 status=completed / failed
    5. 返回 {"report_id": int, "version": int}
    """
    if watchlist is None:
        watchlist = []

    version = _get_next_version(db)
    config = get_or_create_report_config(db)
    (
        market_prompt,
        capital_prompt,
        geopolitics_prompt,
        sector_prompt,
        stocks_prompt,
        yield_curve_prompt,
        x_monitor_prompt,
    ) = _resolve_prompts(config)
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
        yield_curve_system_prompt=yield_curve_prompt,
        x_monitor_system_prompt=x_monitor_prompt,
        watchlist_used=json.dumps(watchlist),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    try:
        # 2. 并行获取数据 + AI 分析
        index_data, sector_data, stocks_data, curve_data, x_data = await asyncio.gather(
            asyncio.to_thread(fetch_index_data),
            asyncio.to_thread(fetch_sector_data),
            get_report_section_stocks(watchlist),
            asyncio.to_thread(fetch_yield_curve_data),
            asyncio.to_thread(fetch_x_tweets_data, db, 7),
        )

        # AI 分析（依赖上面的数据 + 纯 LLM 模块）
        (
            ai_market_summary,
            ai_capital_summary,
            ai_geopolitics_summary,
            ai_sector_summary,
            ai_yield_curve_summary,
            ai_x_monitor_summary,
        ) = await asyncio.gather(
            generate_ai_market_summary(index_data, system_prompt=market_prompt),
            generate_ai_capital_summary(system_prompt=capital_prompt),
            generate_ai_geopolitics_summary(system_prompt=geopolitics_prompt),
            generate_ai_sector_summary(sector_data, system_prompt=sector_prompt),
            generate_ai_yield_curve_summary(curve_data, system_prompt=yield_curve_prompt),
            generate_ai_x_monitor_summary(x_data, system_prompt=x_monitor_prompt),
        )

        # 3. 序列化 JSON 并更新 DB
        report.index_data = json.dumps(index_data, ensure_ascii=False)
        report.sector_data = json.dumps(sector_data, ensure_ascii=False)
        report.watchlist_scores = json.dumps(stocks_data.get("watchlist_scores", []), ensure_ascii=False)
        report.hot_stock_scores = json.dumps(stocks_data.get("hot_stock_scores", []), ensure_ascii=False)
        report.yield_curve_data = json.dumps(curve_data, ensure_ascii=False)
        report.x_tweets_data = json.dumps(x_data, ensure_ascii=False)
        report.ai_market_summary = ai_market_summary
        report.ai_capital_summary = ai_capital_summary
        report.ai_geopolitics_summary = ai_geopolitics_summary
        report.ai_sector_summary = ai_sector_summary
        report.ai_yield_curve_summary = ai_yield_curve_summary
        report.ai_x_monitor_summary = ai_x_monitor_summary
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
