"""板块强度雷达 - 市场无关的通用计算函数

从 sector_strength.py（美股实现）抽取出的纯算法层：
- 只依赖标准 OHLCV DataFrame（列名 [Open, High, Low, Close, Volume]）
- 不涉及数据源、宇宙定义、基准符号
- 供美股 (sector_strength.py) 与 A 股 (sector_strength_cn.py) 共同使用

设计原则：
- 函数以下划线开头保留私有意图，但从本文件公开导出
- 涉及的时间尺度参数（span=20, sma=21, series_len=130）保持市场无关的默认值，
  美股/A 股均按 130 交易日历史窗口输出
"""

from typing import Optional

import numpy as np
import pandas as pd

# ─── RS 复合权重（多市场统一） ───
RS_WEIGHTS = {"5d": 0.10, "15d": 0.20, "30d": 0.30, "60d": 0.40}


# ─── 收益率与表现 ───

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
# 先对收盘价取自然对数再算 EMA，而非 ln(EMA(close))。

# 阈值带（减法版，单位 %）
_LOGBIAS_OVERHEATED = 15.0
_LOGBIAS_MODERATE = 5.0
_LOGBIAS_ABOVE = 0.0
_LOGBIAS_EXIT = -5.0


def _classify_zone(v: Optional[float]) -> str:
    """根据 LOGBIAS 数值划分状态区间"""
    if v is None:
        return "unknown"
    if v > _LOGBIAS_OVERHEATED:
        return "overheated"
    if v >= _LOGBIAS_MODERATE:
        return "moderate"
    if v >= _LOGBIAS_ABOVE:
        return "above"
    if v >= _LOGBIAS_EXIT:
        return "hold"
    return "exit"


def _compute_logbias(df: pd.DataFrame, span: int = 20, series_len: int = 130) -> dict:
    """计算对数均线偏离度（减法版）及其历史序列。

    series_len 默认 130 个交易日（覆盖近 6 个月）。
    """
    closes = df["Close"].dropna()
    closes = closes[closes > 0]

    warmup_period = span * 2
    if len(closes) < warmup_period:
        return {"value": None, "zone": "unknown", "series": [], "dates": [],
                "log_close": [], "ema": []}

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
        "log_close": [round(float(v), 3) for v in ln_close.tail(series_len)],
        "ema": [round(float(v), 3) for v in ema.tail(series_len)],
    }


# ─── 相对强度 (RS) ───

def _compute_rs(etf_closes: pd.Series, benchmark_closes: pd.Series) -> dict:
    """计算 ETF 相对于基准的 RS 指标（美股基准=SPY，A 股基准=沪深300 ETF）"""
    rs = {}
    for label, days in [("5d", 5), ("15d", 15), ("30d", 30), ("60d", 60)]:
        etf_ret = _compute_return(etf_closes, days)
        bench_ret = _compute_return(benchmark_closes, days)
        if etf_ret is not None and bench_ret is not None:
            rs[f"rs_{label}"] = round(etf_ret - bench_ret, 2)
        else:
            rs[f"rs_{label}"] = None

    composite = 0.0
    valid_weight = 0.0
    for label, weight in RS_WEIGHTS.items():
        val = rs.get(f"rs_{label}")
        if val is not None:
            composite += val * weight
            valid_weight += weight
    rs["composite"] = round(composite / valid_weight, 2) if valid_weight > 0 else None

    return rs


def _compute_rs_series(
    etf_closes: pd.Series,
    benchmark_closes: pd.Series,
    sma_period: int = 21,
    series_len: int = 130,
) -> dict:
    """Mansfield 相对强弱线 (RS Line) 及其历史序列。

    RP  = ETF_Close / Benchmark_Close
    RSM = (RP / SMA(RP, N) - 1) × 100
    """
    aligned = pd.concat(
        [etf_closes.dropna(), benchmark_closes.dropna()],
        axis=1, keys=["etf", "bench"],
    ).dropna()
    aligned = aligned[(aligned["etf"] > 0) & (aligned["bench"] > 0)]

    if len(aligned) < sma_period + 5:
        return {"value": None, "series": [], "dates": []}

    rp = aligned["etf"] / aligned["bench"]
    sma = rp.rolling(sma_period).mean()
    rsm = ((rp / sma) - 1) * 100
    rsm = rsm.dropna()

    if rsm.empty:
        return {"value": None, "series": [], "dates": []}

    current = round(float(rsm.iloc[-1]), 2)
    tail = rsm.tail(series_len)
    return {
        "value": current,
        "series": [round(float(v), 2) for v in tail],
        "dates": [d.strftime("%m-%d") for d in tail.index],
    }


# ─── 资金流向信号 ───

def _compute_flow(df: pd.DataFrame) -> dict:
    """计算资金流向代理指标"""
    if len(df) < 20:
        return {"flow_5d": None, "vol_surge": None, "direction": "neutral", "accumulation": None}

    closes = df["Close"]
    volumes = df["Volume"]
    daily_returns = closes.pct_change()

    last_20 = df.tail(20)
    avg_dollar_vol = (last_20["Close"] * last_20["Volume"]).mean()

    last_5_returns = daily_returns.tail(5)
    last_5_volumes = volumes.tail(5)
    flow_5d_raw = (last_5_returns * last_5_volumes).sum()
    flow_5d = round(float(flow_5d_raw / avg_dollar_vol), 4) if avg_dollar_vol > 0 else 0.0

    vol_5d_avg = volumes.tail(5).mean()
    vol_20d_avg = volumes.tail(20).mean()
    vol_surge = round(float(vol_5d_avg / vol_20d_avg), 2) if vol_20d_avg > 0 else 1.0

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
    accumulation = round(up_vol_days / 9, 2)

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
