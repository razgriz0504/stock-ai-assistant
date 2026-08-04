"""净 Gamma 敞口（Net GEX）计算模块。

数据流（配合富途 OpenD）：
  get_option_chain（静态链）→ get_market_snapshot（行情/OI）→ merge
  → 真实 spot 下固定 IV（Sticky Strike 假设）→ 逐行权价 GEX → 聚合 + Zero Gamma

符号约定（公共数据标准，SqueezeMetrics/SpotGamma naive 口径）：
  Call GEX 记正、Put GEX 记负；这是对 dealer 持仓方向的模型假设，
  不是对做市商真实账簿的直接观察。Net GEX > 0 对应 dealer 净长 gamma
  （对冲盘逆势、平抑波动），< 0 对应净短 gamma（对冲盘顺势、放大波动）。
  仅作波动率情境参考，不构成方向预测。

Zero Gamma 计算要点：扫描假想 spot 网格时，波动率微笑按行权价固定
（Sticky Strike），只把现货价 S 作为变量重算 gamma，绝不使用假想价格
重新反推 IV。
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

logger = logging.getLogger(__name__)

SNAPSHOT_CHUNK = 400          # 富途单次快照上限（合约数）
DEFAULT_MULTIPLIER = 100.0    # 美股期权合约乘数兜底
SIGN_CONV = {"CALL": 1.0, "PUT": -1.0}
GRID_SPAN = 0.2               # Zero Gamma 扫描范围：±20% spot
GRID_POINTS = 121


# ─── Black-Scholes 基础函数（含边缘防护） ───

def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """单合约 gamma（标的价格变动 1 元，delta 的变动量，按每股计）。"""
    if T <= 0 or sigma <= 0:
        return 0.0
    denom = sigma * math.sqrt(T)
    if denom < 1e-8:                     # 极低 IV / 极短期限，防除零溢出
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / denom
    return norm.pdf(d1) / (S * denom)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str) -> float:
    """欧式期权 BS 定价（反推 IV 内部同样需要分母防护）。"""
    denom = sigma * math.sqrt(T)
    if denom < 1e-8:                     # 退化情形近似内在价值
        return max(S - K, 0.0) if option_type == "CALL" else max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / denom
    d2 = d1 - denom
    if option_type == "CALL":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(price: float, S: float, K: float, T: float, r: float,
                option_type: str, lo: float = 1e-4, hi: float = 5.0) -> float:
    """二分法从市场价格反解隐含波动率。"""
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs_price(S, K, T, r, mid, option_type) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ─── 数据准备：真实 spot 下一次性固定 IV（Sticky Strike） ───

def compute_gex(chain: pd.DataFrame, spot: float, r: float = 0.045,
                min_oi: int = 0, min_t: float = 1 / 365,
                max_t: float = 60 / 365) -> pd.DataFrame:
    """产出带 T / sign / multiplier / sigma 列的 DataFrame，不在此算 gamma。

    sigma 三层来源（只调用一次，供后续网格扫描复用）：
      ① 快照自带 IV（option_implied_volatility）
      ② 缺失且有成交价 → BS 反推
      ③ 仍缺失 → 同到期日有效 IV 中位数
    """
    df = chain.copy()
    if df.empty:
        return df
    df = df[df["open_interest"] >= min_oi].reset_index(drop=True)
    today = pd.Timestamp.today().normalize()
    df["T"] = (pd.to_datetime(df["expire_date"]) - today).dt.days / 365.0
    df = df[(df["T"] >= min_t) & (df["T"] <= max_t)].reset_index(drop=True)
    df["sign"] = df["option_type"].map(SIGN_CONV)
    df["multiplier"] = df.get("lot_size", pd.Series(
        DEFAULT_MULTIPLIER, index=df.index)).fillna(DEFAULT_MULTIPLIER).astype(float)

    df["sigma"] = df.get("iv_snap", np.nan)
    df.loc[df["sigma"] <= 0, "sigma"] = np.nan
    mask = df["sigma"].isna() & (df["last_price"] > 0)
    df.loc[mask, "sigma"] = df.loc[mask].apply(
        lambda row: implied_vol(row["last_price"], spot, row["strike_price"],
                                row["T"], r, row["option_type"]), axis=1)
    df["sigma"] = df.groupby("expire_date")["sigma"].transform(
        lambda s: s.fillna(s.median()))
    df["sigma"] = df["sigma"].fillna(0.3).astype(float)

    # 真实 spot 下的逐合约 GEX（供报告/调试；Zero Gamma 扫描用 calc_gamma_only）
    gamma = _gamma_vec(spot, df["strike_price"].to_numpy(), df["T"].to_numpy(),
                       r, df["sigma"].to_numpy())
    gex_1dollar = df["sign"] * gamma * spot * df["open_interest"] * df["multiplier"]
    df["gex_1pct"] = gex_1dollar * spot * 0.01
    return df


# ─── 网格扫描：固定 IV，仅把 S 作为变量重算 gamma ───

def _gamma_vec(S: float, K: np.ndarray, T: np.ndarray, r: float,
               sigma: np.ndarray) -> np.ndarray:
    """向量化 gamma，等价于带防护的 bs_gamma。"""
    denom = sigma * np.sqrt(T)
    denom = np.where(denom < 1e-8, np.nan, denom)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / denom
    gamma = np.exp(-0.5 * d1**2) / np.sqrt(2 * np.pi) / (S * denom)
    return np.nan_to_num(gamma, nan=0.0)


def calc_gamma_only(df_iv: pd.DataFrame, hypothetical_spot: float,
                    r: float = 0.045) -> float:
    """仅在假想 spot 下重算 gamma + GEX；sigma 保持网格扫描前固定不变。"""
    gamma = _gamma_vec(hypothetical_spot, df_iv["strike_price"].to_numpy(),
                       df_iv["T"].to_numpy(), r, df_iv["sigma"].to_numpy())
    gex_1dollar = (df_iv["sign"].to_numpy() * gamma * hypothetical_spot
                   * df_iv["open_interest"].to_numpy()
                   * df_iv["multiplier"].to_numpy())
    return float((gex_1dollar * hypothetical_spot * 0.01).sum())  # 每 1% 口径


def zero_gamma(df_iv: pd.DataFrame, spot: float, r: float = 0.045,
               grid: np.ndarray | None = None,
               n_points: int = GRID_POINTS) -> tuple[float, float]:
    """扫描假想 spot 找 Net GEX 过零点（含线性插值精确定位）。"""
    if df_iv.empty:
        return float(spot), 0.0
    if grid is None:
        grid = np.linspace((1 - GRID_SPAN) * spot, (1 + GRID_SPAN) * spot, n_points)
    prev_s, prev_gex = None, None
    for s in grid:
        net = calc_gamma_only(df_iv, s, r)
        if prev_gex is not None and prev_gex * net < 0:
            # 线性插值精确定位零点
            s_zero = prev_s + (s - prev_s) * (-prev_gex) / (net - prev_gex)
            return float(s_zero), 0.0
        prev_s, prev_gex = s, net
    return float(prev_s), float(prev_gex)


# ─── 汇总报告（API 直接消费） ───

def build_gex_report(chain: pd.DataFrame, spot: float, r: float = 0.045,
                     min_oi: int = 0, min_t: float = 1 / 365,
                     max_t: float = 60 / 365, max_expiries: int = 6) -> dict:
    """当前净 GEX + Zero Gamma + 按行权价/到期日聚合 + 扫描曲线。"""
    filters = {
        "min_oi": min_oi,
        "min_t_days": round(min_t * 365, 2),
        "max_t_days": round(max_t * 365, 2),
        "max_expiries": max_expiries,
    }
    df = compute_gex(chain, spot, r=r, min_oi=min_oi, min_t=min_t, max_t=max_t)
    if df.empty:
        return {
            "spot": float(spot), "net_gex_1pct": 0.0, "zero_gamma": None,
            "call_gex_1pct": 0.0, "put_gex_1pct": 0.0, "contracts": 0,
            "strikes": [], "expiries": [], "curve": [],
            "filters": filters,
            "sign_convention": "call=+1 / put=-1",
            "warning": "过滤后无有效期权数据（OI/到期日过滤过严或期权链为空）",
        }

    call_gex = float(df.loc[df["sign"] > 0, "gex_1pct"].sum())
    put_gex = float(df.loc[df["sign"] < 0, "gex_1pct"].sum())
    net = call_gex + put_gex

    # Zero Gamma 扫描曲线 + 零点（网格内无过零点时返回 None，避免误读为端点值）
    grid = np.linspace((1 - GRID_SPAN) * spot, (1 + GRID_SPAN) * spot, GRID_POINTS)
    curve = [{"spot": round(float(s), 4),
              "net_gex_1pct": round(calc_gamma_only(df, s, r), 2)} for s in grid]
    zg, _ = zero_gamma(df, spot, r, grid=grid)
    zero_gamma_level = round(float(zg), 4) if grid[0] < zg < grid[-1] else None

    # 按行权价聚合（Call/Put/Net GEX + OI）
    strikes: list[dict] = []
    for k, g in df.groupby("strike_price"):
        calls, puts = g[g["sign"] > 0], g[g["sign"] < 0]
        strikes.append({
            "strike": float(k),
            "call_gex_1pct": round(float(calls["gex_1pct"].sum()), 2),
            "put_gex_1pct": round(float(puts["gex_1pct"].sum()), 2),
            "net_gex_1pct": round(float(g["gex_1pct"].sum()), 2),
            "call_oi": int(calls["open_interest"].sum()),
            "put_oi": int(puts["open_interest"].sum()),
        })
    strikes.sort(key=lambda x: x["strike"])

    # 按到期日聚合
    expiries: list[dict] = []
    for exp, g in df.groupby("expire_date"):
        calls, puts = g[g["sign"] > 0], g[g["sign"] < 0]
        expiries.append({
            "expire_date": str(exp),
            "t_days": int(round(float(g["T"].iloc[0]) * 365)),
            "call_gex_1pct": round(float(calls["gex_1pct"].sum()), 2),
            "put_gex_1pct": round(float(puts["gex_1pct"].sum()), 2),
            "net_gex_1pct": round(float(g["gex_1pct"].sum()), 2),
            "contracts": int(len(g)),
            "oi_total": int(g["open_interest"].sum()),
        })
    expiries.sort(key=lambda x: x["expire_date"])

    return {
        "spot": float(spot),
        "r": r,
        "net_gex_1pct": round(net, 2),
        "zero_gamma": zero_gamma_level,
        "call_gex_1pct": round(call_gex, 2),
        "put_gex_1pct": round(put_gex, 2),
        "contracts": int(len(df)),
        "strikes": strikes,
        "expiries": expiries,
        "curve": curve,
        "filters": filters,
        "sign_convention": "call=+1 / put=-1",
    }
