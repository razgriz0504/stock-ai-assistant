"""板块强度雷达 - A 股实现

结构完全对齐美股 (sector_strength.py):
- 数据源: akshare (fund_etf_hist_em)
- 基准: 沪深 300 ETF (510300)
- 宇宙: 12 只一级行业 ETF + 20 只主题 ETF = 32 只
- 核心计算函数复用 sector_strength_common (RS/logbias/flow/rs_line)

API 响应结构与美股完全一致，前端只需靠 market Tab 切换 URL 即可。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import pandas as pd

from app.data.sector_strength_common import (
    _compute_flow,
    _compute_logbias,
    _compute_performance,
    _compute_rs,
    _compute_rs_series,
)

logger = logging.getLogger(__name__)

# ─── A 股 ETF 宇宙定义 ───

# 一级行业组（对标 SPDR）
CN_SECTOR_ETFS = {
    "512000": "券商",     "512800": "银行",       "512660": "军工",
    "512690": "白酒",     "512010": "医药",       "512200": "地产",
    "512400": "有色",     "515220": "煤炭",       "515210": "钢铁",
    "159928": "消费",     "512580": "环保",       "515170": "食品饮料",
}

# 主题组（对标 THEMATIC）
CN_THEMATIC_ETFS = {
    "512480": "半导体",       "515030": "新能源车",   "515790": "光伏",
    "159819": "人工智能",     "512290": "生物医药",   "515120": "创新药",
    "516110": "汽车",         "515050": "5G通信",     "516630": "云计算",
    "512980": "传媒",         "515700": "新能源",     "159611": "电力",
    "159755": "电池",         "512170": "医疗",       "515880": "通信",
    "159781": "机器人",       "516010": "游戏",       "159732": "消费电子",
    "159770": "工业母机",     "159766": "旅游",
}

# 合并全部 ETF
ALL_CN_ETFS = {**CN_SECTOR_ETFS, **CN_THEMATIC_ETFS}

# 基准: 沪深 300 ETF
BENCHMARK_CN = "510300"
BENCHMARK_CN_NAME = "沪深300"

# 缓存（与美股独立命名空间）
_cache_cn: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 分钟


# ─── akshare 单只 ETF 拉取 ───

def _fetch_one_etf_cn(symbol: str, start_date: str, end_date: str) -> tuple[str, pd.DataFrame | None]:
    """使用 akshare 拉取单只 ETF 的日线，返回与 yfinance 相同格式的 DataFrame。

    akshare fund_etf_hist_em 返回列（中文）:
        日期 / 开盘 / 收盘 / 最高 / 最低 / 成交量 / 成交额 / 振幅 / 涨跌幅 / 涨跌额 / 换手率

    转成标准列 [Open, High, Low, Close, Volume] + DatetimeIndex。
    """
    try:
        import akshare as ak
        raw = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",  # 前复权
        )
        if raw is None or raw.empty:
            return symbol, None

        df = pd.DataFrame({
            "Open": pd.to_numeric(raw["开盘"], errors="coerce"),
            "High": pd.to_numeric(raw["最高"], errors="coerce"),
            "Low": pd.to_numeric(raw["最低"], errors="coerce"),
            "Close": pd.to_numeric(raw["收盘"], errors="coerce"),
            "Volume": pd.to_numeric(raw["成交量"], errors="coerce"),
        })
        df.index = pd.to_datetime(raw["日期"])
        df = df.dropna(subset=["Close"])
        df = df[df["Close"] > 0]
        if len(df) < 5:
            return symbol, None
        return symbol, df
    except Exception as e:
        logger.warning(f"akshare fetch {symbol} failed: {e}")
        return symbol, None


def _batch_download_cn(symbols: list[str], lookback_days: int = 260) -> dict[str, pd.DataFrame]:
    """并行拉取 A 股 ETF 日线（akshare 无批量接口，用线程池并发）。

    lookback_days=260 覆盖约 12 个自然月 ≈ 240 交易日，供 60 日收益率与 130 日 logbias 序列使用。
    """
    all_symbols = symbols.copy()
    if BENCHMARK_CN not in all_symbols:
        all_symbols.append(BENCHMARK_CN)

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    logger.info(f"CN batch downloading {len(all_symbols)} ETFs "
                f"({start_str}~{end_str}) via akshare...")

    result: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(_fetch_one_etf_cn, sym, start_str, end_str)
            for sym in all_symbols
        ]
        for fut in as_completed(futures):
            sym, df = fut.result()
            if df is not None:
                result[sym] = df

    logger.info(f"CN successfully loaded {len(result)}/{len(all_symbols)} ETFs")
    return result


# ─── 主入口 ───

def fetch_enhanced_sector_data_cn(use_cache: bool = True) -> dict:
    """
    获取增强 A 股板块数据：32 ETF + 沪深300 基准，含 RS 和资金流向。

    响应结构与美股 fetch_enhanced_sector_data 完全一致，前端可通用。

    Args:
        use_cache: True 使用 5 分钟缓存

    Returns:
        结构化字典，包含 benchmark、sectors 列表、rankings
    """
    global _cache_cn

    if use_cache and _cache_cn["data"] and (time.time() - _cache_cn["ts"]) < _CACHE_TTL:
        logger.info("Using cached CN sector strength data")
        return _cache_cn["data"]

    etf_symbols = list(ALL_CN_ETFS.keys())
    histories = _batch_download_cn(etf_symbols)

    if not histories or BENCHMARK_CN not in histories:
        logger.error("Failed to fetch benchmark (沪深300) data")
        return {"generated_at": "", "benchmark": {}, "sectors": [], "rankings": {}}

    bench_df = histories[BENCHMARK_CN]
    bench_closes = bench_df["Close"]
    bench_perf = _compute_performance(bench_df)

    sectors = []
    for symbol, name in ALL_CN_ETFS.items():
        if symbol not in histories:
            continue
        df = histories[symbol]

        perf = _compute_performance(df)
        rs = _compute_rs(df["Close"], bench_closes)
        rs_line = _compute_rs_series(df["Close"], bench_closes)
        flow = _compute_flow(df)
        logbias = _compute_logbias(df)

        # category 对齐美股: sector=一级行业 / thematic=主题（前端 category 字段兼容）
        category = "sector" if symbol in CN_SECTOR_ETFS else "thematic"

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

    sectors_above_bench = sum(
        1 for s in sectors
        if s.get("chg_30d") is not None and bench_perf.get("chg_30d") is not None
        and s["chg_30d"] > bench_perf["chg_30d"]
    )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": "cn",
        "benchmark": {
            "symbol": BENCHMARK_CN,
            "name": BENCHMARK_CN_NAME,
            "current": bench_perf["current"],
            "chg_5d": bench_perf["chg_5d"],
            "chg_15d": bench_perf["chg_15d"],
            "chg_30d": bench_perf["chg_30d"],
            "chg_60d": bench_perf["chg_60d"],
            "logbias": _compute_logbias(bench_df),
        },
        "sectors": sorted_by_rs,
        "rankings": rankings,
        "summary_stats": {
            "total_etfs": len(sectors),
            "sectors_above_bench_30d": sectors_above_bench,
            "sectors_below_bench_30d": len(sectors) - sectors_above_bench,
            "strongest_theme": sorted_by_rs[0]["name"] if sorted_by_rs else "",
            "strongest_symbol": sorted_by_rs[0]["symbol"] if sorted_by_rs else "",
        },
    }

    _cache_cn["data"] = result
    _cache_cn["ts"] = time.time()

    logger.info(f"CN enhanced sector data: {len(sectors)} ETFs processed, "
                f"{sectors_above_bench} above {BENCHMARK_CN_NAME} 30d")
    return result
