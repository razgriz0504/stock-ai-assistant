"""板块强度雷达 - 核心数据层

提供 41 只 ETF（11 SPDR 一级行业 + 30 主题 ETF）的：
- 多时间框架表现 (5d/15d/30d/60d)
- 相对强度 RS（vs SPY 超额收益）
- 资金流向信号（量价代理）
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

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

# RS 复合权重
RS_WEIGHTS = {"5d": 0.10, "15d": 0.20, "30d": 0.30, "60d": 0.40}

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


# ─── 性能指标计算 ───

def _compute_return(closes: pd.Series, days: int) -> Optional[float]:
    """计算 N 日收益率（百分比）"""
    if len(closes) < days + 1:
        return None
    current = closes.iloc[-1]
    past = closes.iloc[-(days + 1)]
    if past == 0 or pd.isna(past) or pd.isna(current):
        return None
    return round(((current - past) / past) * 100, 2)


def _compute_performance(df: pd.DataFrame) -> dict:
    """计算单个 ETF 的多时间框架表现"""
    closes = df["Close"]
    current = float(closes.iloc[-1])

    # 量比
    volumes = df["Volume"]
    vol_ma20 = volumes.rolling(20).mean().iloc[-1] if len(volumes) >= 20 else volumes.mean()
    vol_recent = volumes.tail(5).mean()
    vol_ratio = round(float(vol_recent / vol_ma20), 2) if vol_ma20 > 0 else 1.0

    return {
        "current": round(current, 2),
        "chg_5d": _compute_return(closes, 5),
        "chg_15d": _compute_return(closes, 15),
        "chg_30d": _compute_return(closes, 30),
        "chg_60d": _compute_return(closes, 60),
        "vol_ratio": vol_ratio,
    }


# ─── 对数均线偏离度 (LOGBIAS) ───
# 刘晨明/广发策略「对数均线偏离度」减法版：
#   EMA20 = EMA(ln(Close), 20)
#   LOGBIAS = (ln(Close) - EMA20) × 100
# 注意：先对收盘价取自然对数再算 EMA，而非 ln(EMA(close))。

# 阈值带（减法版，单位 %）
_LOGBIAS_OVERHEATED = 15.0   # > 15%   过热，别追
_LOGBIAS_MODERATE = 5.0      # 5%~15%  适中，可追
_LOGBIAS_ABOVE = 0.0         # 0%~5%   均线上方，安心
_LOGBIAS_EXIT = -5.0         # -5%~0%  刚跌破，坚守；< -5% 失速，离场


def _classify_zone(v: Optional[float]) -> str:
    """根据 LOGBIAS 数值划分状态区间"""
    if v is None:
        return "unknown"
    if v > _LOGBIAS_OVERHEATED:
        return "overheated"   # 过热
    if v >= _LOGBIAS_MODERATE:
        return "moderate"     # 适中
    if v >= _LOGBIAS_ABOVE:
        return "above"        # 均线上方
    if v >= _LOGBIAS_EXIT:
        return "hold"         # 刚跌破，坚守
    return "exit"             # 失速，离场


def _compute_logbias(df: pd.DataFrame, span: int = 20, series_len: int = 130) -> dict:
    """计算对数均线偏离度（减法版）及其历史序列

    series_len 默认 130 个交易日（覆盖近 6 个月），前端据此截取 6/3/1 个月三段展示。
    """
    closes = df["Close"].dropna()
    closes = closes[closes > 0]  # 防御异常脏数据：价格必须 > 0，否则 np.log 返回 -inf

    # EMA 需要预热期消除初始值影响，20 日 EMA 至少需 2 倍样本（40 日）才能与通达信等软件对齐
    warmup_period = span * 2
    if len(closes) < warmup_period:
        return {"value": None, "zone": "unknown", "series": [], "dates": []}

    ln_close = np.log(closes)
    ema = ln_close.ewm(span=span, adjust=False).mean()
    logbias = (ln_close - ema) * 100

    current = round(float(logbias.iloc[-1]), 2)
    tail = logbias.tail(series_len)
    return {
        "value": current,
        "zone": _classify_zone(current),
        "series": [round(float(v), 2) for v in tail],
        "dates": [d.strftime("%m-%d") for d in tail.index],
    }


# ─── 相对强度 (RS) ───

def _compute_rs(etf_closes: pd.Series, spy_closes: pd.Series) -> dict:
    """计算 ETF 相对于 SPY 的 RS 指标"""
    rs = {}
    for label, days in [("5d", 5), ("15d", 15), ("30d", 30), ("60d", 60)]:
        etf_ret = _compute_return(etf_closes, days)
        spy_ret = _compute_return(spy_closes, days)
        if etf_ret is not None and spy_ret is not None:
            rs[f"rs_{label}"] = round(etf_ret - spy_ret, 2)
        else:
            rs[f"rs_{label}"] = None

    # 复合 RS
    composite = 0.0
    valid_weight = 0.0
    for label, weight in RS_WEIGHTS.items():
        val = rs.get(f"rs_{label}")
        if val is not None:
            composite += val * weight
            valid_weight += weight
    rs["composite"] = round(composite / valid_weight, 2) if valid_weight > 0 else None

    return rs


# ─── 资金流向信号 ───

def _compute_flow(df: pd.DataFrame) -> dict:
    """计算资金流向代理指标"""
    if len(df) < 20:
        return {"flow_5d": None, "vol_surge": None, "direction": "neutral", "accumulation": None}

    closes = df["Close"]
    volumes = df["Volume"]
    daily_returns = closes.pct_change()

    # 1. Dollar volume flow (5d): Σ(daily_return × volume) / avg_dollar_volume_20d
    last_20 = df.tail(20)
    avg_dollar_vol = (last_20["Close"] * last_20["Volume"]).mean()

    last_5_returns = daily_returns.tail(5)
    last_5_volumes = volumes.tail(5)
    flow_5d_raw = (last_5_returns * last_5_volumes).sum()
    flow_5d = round(float(flow_5d_raw / avg_dollar_vol), 4) if avg_dollar_vol > 0 else 0.0

    # 2. Volume surge: avg(vol_5d) / avg(vol_20d)
    vol_5d_avg = volumes.tail(5).mean()
    vol_20d_avg = volumes.tail(20).mean()
    vol_surge = round(float(vol_5d_avg / vol_20d_avg), 2) if vol_20d_avg > 0 else 1.0

    # 3. Accumulation score: 近 10 日中放量上涨天数 / 10
    last_10 = df.tail(10)
    last_10_returns = last_10["Close"].pct_change()
    last_10_volumes = last_10["Volume"]
    vol_avg = volumes.tail(20).mean()
    up_vol_days = 0
    for i in range(1, len(last_10)):
        ret = last_10_returns.iloc[i]
        vol = last_10_volumes.iloc[i]
        if not pd.isna(ret) and ret > 0 and not pd.isna(vol) and vol > vol_avg:
            up_vol_days += 1
    accumulation = round(up_vol_days / 9, 2)  # 9 because pct_change loses first row

    # 4. Flow direction
    if flow_5d > 0.05 and vol_surge > 1.2:
        direction = "inflow"
    elif flow_5d < -0.05 and vol_surge > 1.2:
        direction = "outflow"
    else:
        direction = "neutral"

    return {
        "flow_5d": flow_5d,
        "vol_surge": vol_surge,
        "direction": direction,
        "accumulation": accumulation,
    }


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
