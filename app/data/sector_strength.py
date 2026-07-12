"""板块强度雷达 - 美股实现（数据源 + 宇宙 + 调度）

提供 41 只 ETF（11 SPDR 一级行业 + 30 主题 ETF）的：
- 多时间框架表现 (5d/15d/30d/60d)
- 相对强度 RS（vs SPY 超额收益）
- 资金流向信号（量价代理）

核心计算函数以抓取到 :mod:`app.data.sector_strength_common`，与 A 股共享。
"""

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from app.data.sector_strength_common import (
    RS_WEIGHTS,
    _compute_flow,
    _compute_logbias,
    _compute_performance,
    _compute_return,
    _compute_rs,
    _compute_rs_series,
)

logger = logging.getLogger(__name__)

# ─── ETF 宇宙定义 ───

SPDR_SECTORS = {
    "XLK": "科技", "XLF": "金融", "XLE": "能源", "XLV": "医疗",
    "XLY": "非必需消费", "XLP": "必需消费", "XLI": "工业",
    "XLB": "材料", "XLRE": "房地产", "XLC": "通信服务", "XLU": "公用事业",
}

THEMATIC_ETFS = {
    "SMH": "半导体", "SOXX": "半导体(iShares)",
    "XBI": "生物科技", "IBB": "生物制药",
    "CIBR": "网络安全",
    "SKYY": "云计算", "IGV": "软件",
    "ICLN": "清洁能源", "TAN": "太阳能",
    "BOTZ": "AI与机器人", "AIQ": "AI基础设施",
    "FINX": "金融科技", "BLOK": "区块链",
    "ITA": "航空航天与国防",
    "PAVE": "基础设施", "XHB": "住宅建筑",
    "XRT": "零售",
    "GDX": "黄金矿业", "URA": "铀与核能", "XME": "金属与矿业",
    "XOP": "油气勘探",
    "KRE": "区域银行",
    "FDN": "互联网",
    "LIT": "锂电与电动车",
    "VIG": "红利成长",
}

# 合并全部 ETF
ALL_ETFS = {**SPDR_SECTORS, **THEMATIC_ETFS}

BENCHMARK = "SPY"

# 缓存
_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 分钟


# ─── 批量数据获取 ───

def _batch_download(symbols: list[str], period: str = "3mo") -> dict[str, pd.DataFrame]:
    """使用 yf.download 批量获取历史行情，返回 {symbol: DataFrame}"""
    all_symbols = symbols.copy()
    if BENCHMARK not in all_symbols:
        all_symbols.append(BENCHMARK)

    logger.info(f"Batch downloading {len(all_symbols)} ETFs (period={period})...")
    try:
        raw = yf.download(all_symbols, period=period, progress=False, threads=True)
    except Exception as e:
        logger.error(f"yf.download failed: {e}")
        return {}

    if raw.empty:
        logger.warning("yf.download returned empty DataFrame")
        return {}

    result = {}
    for symbol in all_symbols:
        try:
            # yf.download 返回 MultiIndex columns: (field, symbol)
            if isinstance(raw.columns, pd.MultiIndex):
                df = raw.xs(symbol, level=1, axis=1).copy()
            else:
                # 单 symbol 情况
                df = raw.copy()
            df = df.dropna(subset=["Close"])
            if len(df) >= 5:
                result[symbol] = df
        except Exception:
            continue

    logger.info(f"Successfully loaded {len(result)}/{len(all_symbols)} ETFs")
    return result


# ─── 性能指标计算（迁移到 sector_strength_common） ───


# ─── 主入口 ───

def fetch_enhanced_sector_data(use_cache: bool = True) -> dict:
    """
    获取增强板块数据：41 ETF + SPY 基准，含 RS 和资金流向。

    Args:
        use_cache: True 使用 5 分钟缓存（独立页面），False 强制刷新（周报生成）

    Returns:
        结构化字典，包含 benchmark、sectors 列表、rankings
    """
    global _cache

    # 检查缓存
    if use_cache and _cache["data"] and (time.time() - _cache["ts"]) < _CACHE_TTL:
        logger.info("Using cached sector strength data")
        return _cache["data"]

    # 批量下载
    etf_symbols = list(ALL_ETFS.keys())
    histories = _batch_download(etf_symbols, period="6mo")

    if not histories or BENCHMARK not in histories:
        logger.error("Failed to fetch benchmark (SPY) data")
        return {"generated_at": "", "benchmark": {}, "sectors": [], "rankings": {}}

    spy_df = histories[BENCHMARK]
    spy_closes = spy_df["Close"]
    spy_perf = _compute_performance(spy_df)

    # 处理每个 ETF
    sectors = []
    for symbol, name in ALL_ETFS.items():
        if symbol not in histories:
            continue
        df = histories[symbol]

        perf = _compute_performance(df)
        rs = _compute_rs(df["Close"], spy_closes)
        rs_line = _compute_rs_series(df["Close"], spy_closes)
        flow = _compute_flow(df)
        logbias = _compute_logbias(df)

        category = "spdr" if symbol in SPDR_SECTORS else "thematic"

        sectors.append({
            "symbol": symbol,
            "name": name,
            "category": category,
            "current": perf["current"],
            "chg_5d": perf["chg_5d"],
            "chg_15d": perf["chg_15d"],
            "chg_30d": perf["chg_30d"],
            "chg_60d": perf["chg_60d"],
            "vol_ratio": perf["vol_ratio"],
            "rs": rs,
            "rs_line": rs_line,
            "flow": flow,
            "logbias": logbias,
        })

    # 排序排名
    def _safe_composite(s):
        v = s.get("rs", {}).get("composite")
        return v if v is not None else -999

    def _safe_chg30(s):
        v = s.get("chg_30d")
        return v if v is not None else -999

    def _safe_accumulation(s):
        v = s.get("flow", {}).get("accumulation")
        return v if v is not None else -999

    sorted_by_rs = sorted(sectors, key=_safe_composite, reverse=True)
    sorted_by_30d = sorted(sectors, key=_safe_chg30, reverse=True)
    sorted_by_flow = sorted(sectors, key=_safe_accumulation, reverse=True)

    rankings = {
        "by_composite_rs": [s["symbol"] for s in sorted_by_rs[:10]],
        "by_momentum_30d": [s["symbol"] for s in sorted_by_30d[:10]],
        "by_flow_strength": [s["symbol"] for s in sorted_by_flow[:10]],
        "weakest_rs": [s["symbol"] for s in sorted_by_rs[-5:]],
    }

    # 统计
    sectors_above_spy = sum(
        1 for s in sectors
        if s.get("chg_30d") is not None and spy_perf.get("chg_30d") is not None
        and s["chg_30d"] > spy_perf["chg_30d"]
    )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "symbol": BENCHMARK,
            "current": spy_perf["current"],
            "chg_5d": spy_perf["chg_5d"],
            "chg_15d": spy_perf["chg_15d"],
            "chg_30d": spy_perf["chg_30d"],
            "chg_60d": spy_perf["chg_60d"],
            "logbias": _compute_logbias(spy_df),
        },
        "sectors": sorted_by_rs,  # 默认按 RS 排序
        "rankings": rankings,
        "summary_stats": {
            "total_etfs": len(sectors),
            "sectors_above_spy_30d": sectors_above_spy,
            "sectors_below_spy_30d": len(sectors) - sectors_above_spy,
            "strongest_theme": sorted_by_rs[0]["name"] if sorted_by_rs else "",
            "strongest_symbol": sorted_by_rs[0]["symbol"] if sorted_by_rs else "",
        },
    }

    # 更新缓存
    _cache["data"] = result
    _cache["ts"] = time.time()

    logger.info(f"Enhanced sector data: {len(sectors)} ETFs processed, "
                f"{sectors_above_spy} above SPY 30d")
    return result
