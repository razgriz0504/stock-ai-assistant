"""市场环境引擎（红绿灯）- 欧奈尔/Minervini 市场择时体系.

判定要素：
1. 分布日 (Distribution Days)：主要指数单日跌幅 >= 0.2% 且成交量高于前一日，
   视为机构派发。滚动 25 个交易日窗口计数；若之后指数自该分布日收盘
   反弹 >= 5% 则该分布日失效剔除。
2. Follow-Through Day (FTD)：修正低点后的上攻确认日。反弹尝试第 4 天起，
   单日涨幅 >= 1.25% 且成交量高于前一日，确认新一轮上升趋势。
3. 趋势位置：指数收盘价相对 21EMA / 50MA / 200MA。
4. 市场宽度：全 Universe 站上 50/200MA 比例、52 周新高-新低、RS>=80 数量。

红绿灯规则（取两大指数中较差者，宽度做降级修正）：
- RED    : 有效分布日 >= 5，或指数同时跌破 50MA 与 200MA
- YELLOW : 分布日 3-4，或跌破 50MA，或 %>200MA 宽度 < 40%
- GREEN  : 其余（趋势健康且分布日 <= 2）
"""

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

INDEXES = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq"}

# ── 分布日 / FTD 参数 ──
DD_WINDOW = 25            # 分布日滚动窗口（交易日）
DD_DOWN_PCT = -0.2        # 单日跌幅阈值 %
DD_EXPIRE_RALLY = 0.05    # 自分布日收盘反弹 5% 则失效
FTD_MIN_DAY = 4           # FTD 最早出现在反弹尝试第 4 天
FTD_GAIN_PCT = 1.25       # FTD 单日涨幅阈值 %
CORRECTION_PCT = -5.0     # 视为"修正"的最小回撤 %


# ═══════════════════════════════════════════════════════════
# 指数层：数据下载 / 分布日 / FTD / 趋势
# ═══════════════════════════════════════════════════════════

def _download_index_data() -> dict[str, pd.DataFrame]:
    """下载两大指数 1 年日线（Close/Volume），返回 {symbol: DataFrame}"""
    symbols = list(INDEXES.keys())
    data = yf.download(symbols, period="1y", progress=False,
                       group_by="ticker", auto_adjust=False, threads=True)
    result: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return result
    for sym in symbols:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if sym in data.columns.get_level_values(0):
                    df = data[sym]
                else:
                    df = data.xs(sym, level=1, axis=1)
            else:
                df = data
            df = df[["Close", "Volume"]].dropna()
            if len(df) >= 60:
                result[sym] = df
        except Exception as e:
            logger.warning(f"[market] index data parse failed for {sym}: {e}")
    return result


def count_distribution_days(df: pd.DataFrame) -> list[str]:
    """统计滚动窗口内的有效分布日，返回日期列表（已剔除失效分布日）"""
    closes = df["Close"]
    vols = df["Volume"]
    chg = closes.pct_change() * 100
    n = len(df)
    dd_dates: list[str] = []
    for i in range(max(1, n - DD_WINDOW), n):
        if chg.iloc[i] <= DD_DOWN_PCT and vols.iloc[i] > vols.iloc[i - 1]:
            dd_close = closes.iloc[i]
            later = closes.iloc[i + 1:]
            # 之后反弹 >= 5% 则该分布日失效
            if not later.empty and float(later.max()) >= dd_close * (1 + DD_EXPIRE_RALLY):
                continue
            dd_dates.append(str(df.index[i].date()))
    return dd_dates


def detect_ftd(df: pd.DataFrame) -> dict:
    """检测最近 60 个交易日内的修正低点与 Follow-Through Day"""
    win = df.iloc[-60:]
    closes = win["Close"]
    vols = win["Volume"]
    low_pos = int(closes.values.argmin())
    low_close = float(closes.iloc[low_pos])
    high_before = float(closes.iloc[:low_pos + 1].max())
    correction_pct = (low_close / high_before - 1) * 100 if high_before > 0 else 0.0

    ftd = None
    # 低点日记为反弹尝试第 1 天，FTD 最早出现在第 4 天
    after_c = closes.iloc[low_pos:]
    after_v = vols.iloc[low_pos:]
    for d in range(FTD_MIN_DAY - 1, len(after_c)):
        gain = (after_c.iloc[d] / after_c.iloc[d - 1] - 1) * 100
        if gain >= FTD_GAIN_PCT and after_v.iloc[d] > after_v.iloc[d - 1]:
            ftd = {
                "date": str(after_c.index[d].date()),
                "day_of_attempt": d + 1,
                "gain_pct": round(float(gain), 2),
            }
            break

    return {
        "correction_low_date": str(closes.index[low_pos].date()),
        "correction_pct": round(correction_pct, 2),
        "in_correction": correction_pct <= CORRECTION_PCT,
        "days_since_low": len(after_c) - 1,
        "ftd": ftd,
    }


def index_trend(df: pd.DataFrame) -> dict:
    """指数趋势位置：收盘价相对 21EMA / 50MA / 200MA"""
    closes = df["Close"]
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
    ema21 = float(closes.ewm(span=21, adjust=False).mean().iloc[-1])
    ma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None
    ma200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else None
    return {
        "close": round(last, 2),
        "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "ema21": round(ema21, 2),
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "above_ema21": last > ema21,
        "above_ma50": bool(ma50 and last > ma50),
        "above_ma200": bool(ma200 and last > ma200),
        "pct_vs_ma50": round((last / ma50 - 1) * 100, 2) if ma50 else None,
        "pct_vs_ma200": round((last / ma200 - 1) * 100, 2) if ma200 else None,
    }


# ═══════════════════════════════════════════════════════════
# 宽度层：全 Universe 广度指标
# ═══════════════════════════════════════════════════════════

def _extract_close_df(data: pd.DataFrame, universe: list[str]) -> pd.DataFrame | None:
    """从 yf.download 批量结果中提取 Close DataFrame（兼容两种 MultiIndex 结构）"""
    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(data.columns.get_level_values(0).unique())
        if "Close" in level0:
            return data["Close"]
        if len(level0 & set(universe)) > 0:
            try:
                return data.xs("Close", level=1, axis=1)
            except KeyError:
                return None
        return None
    if "Close" in data.columns:
        close_df = data[["Close"]]
        close_df.columns = [universe[0]]
        return close_df
    return None


def compute_breadth(universe: list[str]) -> dict:
    """计算市场宽度：%>50MA、%>200MA、52 周新高/新低、RS>=80 数量"""
    if not universe:
        return {}
    data = yf.download(universe, period="13mo", progress=False,
                       threads=True, auto_adjust=False)
    if data is None or data.empty:
        return {}
    close_df = _extract_close_df(data, universe)
    if close_df is None or close_df.empty:
        return {}
    close_df = close_df.dropna(axis=1, how="all")

    last = close_df.iloc[-1]
    ma50 = close_df.rolling(50).mean().iloc[-1]
    ma200 = close_df.rolling(200).mean().iloc[-1]

    valid50 = last.notna() & ma50.notna()
    valid200 = last.notna() & ma200.notna()
    pct_above_50 = float((last[valid50] > ma50[valid50]).mean() * 100) if valid50.any() else None
    pct_above_200 = float((last[valid200] > ma200[valid200]).mean() * 100) if valid200.any() else None

    # 52 周新高/新低（基于收盘价，含当日）
    roll_max = close_df.rolling(252, min_periods=120).max().iloc[-1]
    roll_min = close_df.rolling(252, min_periods=120).min().iloc[-1]
    valid_hl = last.notna() & roll_max.notna() & roll_min.notna()
    new_highs = int((last[valid_hl] >= roll_max[valid_hl]).sum())
    new_lows = int((last[valid_hl] <= roll_min[valid_hl]).sum())

    # RS>=80 数量（读缓存，不触发全量重算）
    rs_80_count = None
    try:
        from app.data.rs_rating import get_rs_snapshot
        snap = get_rs_snapshot()
        if snap:
            rs_80_count = sum(1 for v in snap.values() if v >= 80)
    except Exception as e:
        logger.debug(f"[market] rs snapshot unavailable: {e}")

    return {
        "universe_size": int(valid50.sum()),
        "pct_above_ma50": round(pct_above_50, 1) if pct_above_50 is not None else None,
        "pct_above_ma200": round(pct_above_200, 1) if pct_above_200 is not None else None,
        "new_highs_52w": new_highs,
        "new_lows_52w": new_lows,
        "nh_nl_diff": new_highs - new_lows,
        "rs_ge_80_count": rs_80_count,
    }


# ═══════════════════════════════════════════════════════════
# 判定层：红绿灯分类
# ═══════════════════════════════════════════════════════════

_SEVERITY = {"green": 0, "yellow": 1, "red": 2}


def classify_regime(index_stats: dict[str, dict], breadth: dict | None) -> tuple[str, list[str]]:
    """根据指数与宽度指标输出 (state, reasons)"""
    state = "green"
    reasons: list[str] = []

    def escalate(to: str, reason: str):
        nonlocal state
        reasons.append(reason)
        if _SEVERITY[to] > _SEVERITY[state]:
            state = to

    for sym, st in index_stats.items():
        name = st.get("name", sym)
        dd = st.get("dd_count", 0)
        trend = st.get("trend", {})
        above_50 = trend.get("above_ma50", False)
        above_200 = trend.get("above_ma200", False)

        if dd >= 5:
            escalate("red", f"{name} 分布日 {dd} 个（≥5，机构大举派发）")
        elif dd >= 3:
            escalate("yellow", f"{name} 分布日 {dd} 个（3-4，派发压力上升）")

        if not above_50 and not above_200:
            escalate("red", f"{name} 同时跌破 50MA 与 200MA")
        elif not above_50:
            escalate("yellow", f"{name} 跌破 50MA")

        ftd = st.get("ftd_info", {})
        if ftd.get("in_correction") and not ftd.get("ftd"):
            escalate("yellow", f"{name} 处于修正中（回撤 {ftd.get('correction_pct')}%），尚未出现 FTD 确认")
        elif ftd.get("in_correction") and ftd.get("ftd"):
            reasons.append(f"{name} 已出现 FTD（{ftd['ftd']['date']}，第 {ftd['ftd']['day_of_attempt']} 天）")

    if breadth:
        p200 = breadth.get("pct_above_ma200")
        if p200 is not None and p200 < 40:
            escalate("yellow", f"市场宽度恶化：仅 {p200}% 个股站上 200MA")
        nh_nl = breadth.get("nh_nl_diff")
        if nh_nl is not None and nh_nl < 0:
            reasons.append(f"52 周新低多于新高（NH-NL = {nh_nl}）")

    if state == "green" and not reasons:
        reasons.append("两大指数趋势健康，分布日压力低")
    return state, reasons


# ═══════════════════════════════════════════════════════════
# 汇总：快照计算与持久化
# ═══════════════════════════════════════════════════════════

def compute_market_snapshot(include_breadth: bool = True) -> dict:
    """计算市场环境快照并 upsert 到 DB，返回完整结果 dict.

    include_breadth=False 时跳过全 Universe 下载（快速路径），
    宽度沿用最近一次快照的值。
    """
    from db.models import SessionLocal, MarketRegimeSnapshot

    start = time.time()
    index_data = _download_index_data()
    if not index_data:
        raise RuntimeError("指数数据下载失败")

    index_stats: dict[str, dict] = {}
    for sym, df in index_data.items():
        dd_dates = count_distribution_days(df)
        index_stats[sym] = {
            "name": INDEXES.get(sym, sym),
            "dd_count": len(dd_dates),
            "dd_dates": dd_dates,
            "trend": index_trend(df),
            "ftd_info": detect_ftd(df),
        }

    breadth: dict = {}
    db = SessionLocal()
    try:
        if include_breadth:
            try:
                from app.screener.universe import get_universe
                breadth = compute_breadth(get_universe())
            except Exception as e:
                logger.warning(f"[market] breadth computation failed: {e}")
        if not breadth:
            # 沿用最近一次快照的宽度数据
            prev = (db.query(MarketRegimeSnapshot)
                    .order_by(MarketRegimeSnapshot.snapshot_date.desc()).first())
            if prev and prev.breadth_json:
                try:
                    breadth = json.loads(prev.breadth_json)
                    if breadth:
                        breadth["stale"] = True
                except Exception:
                    breadth = {}

        state, reasons = classify_regime(index_stats, breadth or None)

        today_et = datetime.now(ET).strftime("%Y-%m-%d")
        # 前一状态 = 今天之前最近一条快照
        prev_row = (db.query(MarketRegimeSnapshot)
                    .filter(MarketRegimeSnapshot.snapshot_date < today_et)
                    .order_by(MarketRegimeSnapshot.snapshot_date.desc()).first())
        prev_state = prev_row.state if prev_row else ""

        row = (db.query(MarketRegimeSnapshot)
               .filter(MarketRegimeSnapshot.snapshot_date == today_et).first())
        if not row:
            row = MarketRegimeSnapshot(snapshot_date=today_et)
            db.add(row)
        row.state = state
        row.prev_state = prev_state
        row.reasons_json = json.dumps(reasons, ensure_ascii=False)
        row.index_stats_json = json.dumps(index_stats, ensure_ascii=False)
        row.breadth_json = json.dumps(breadth, ensure_ascii=False)
        db.commit()

        elapsed = time.time() - start
        logger.info(f"[market] snapshot computed: state={state} "
                    f"(prev={prev_state or 'n/a'}) in {elapsed:.1f}s")
        return {
            "snapshot_date": today_et,
            "state": state,
            "prev_state": prev_state,
            "state_changed": bool(prev_state) and prev_state != state,
            "reasons": reasons,
            "index_stats": index_stats,
            "breadth": breadth,
        }
    finally:
        db.close()


def get_latest_snapshot() -> dict | None:
    """读取最近一条快照（不触发计算）"""
    from db.models import SessionLocal, MarketRegimeSnapshot

    db = SessionLocal()
    try:
        row = (db.query(MarketRegimeSnapshot)
               .order_by(MarketRegimeSnapshot.snapshot_date.desc()).first())
        if not row:
            return None
        today_et = datetime.now(ET).strftime("%Y-%m-%d")
        return {
            "snapshot_date": row.snapshot_date,
            "state": row.state,
            "prev_state": row.prev_state,
            "state_changed": bool(row.prev_state) and row.prev_state != row.state,
            "reasons": json.loads(row.reasons_json or "[]"),
            "index_stats": json.loads(row.index_stats_json or "{}"),
            "breadth": json.loads(row.breadth_json or "{}"),
            "is_stale": row.snapshot_date != today_et,
        }
    finally:
        db.close()


def get_regime_history(days: int = 120) -> list[dict]:
    """读取最近 N 条快照的精简历史（用于前端历史条与宽度曲线）"""
    from db.models import SessionLocal, MarketRegimeSnapshot

    db = SessionLocal()
    try:
        rows = (db.query(MarketRegimeSnapshot)
                .order_by(MarketRegimeSnapshot.snapshot_date.desc())
                .limit(days).all())
        out = []
        for r in reversed(rows):
            try:
                breadth = json.loads(r.breadth_json or "{}")
            except Exception:
                breadth = {}
            try:
                idx = json.loads(r.index_stats_json or "{}")
            except Exception:
                idx = {}
            dd_max = max((v.get("dd_count", 0) for v in idx.values()), default=0)
            out.append({
                "date": r.snapshot_date,
                "state": r.state,
                "dd_max": dd_max,
                "pct_above_ma50": breadth.get("pct_above_ma50"),
                "pct_above_ma200": breadth.get("pct_above_ma200"),
                "nh_nl_diff": breadth.get("nh_nl_diff"),
            })
        return out
    finally:
        db.close()


def get_current_risk_pct(settings_row) -> tuple[float, str]:
    """根据最新红绿灯状态返回 (建议单笔风险%, 状态)。无快照时按黄灯保守处理。"""
    snap = get_latest_snapshot()
    state = snap["state"] if snap else "yellow"
    mapping = {
        "green": settings_row.risk_pct_green,
        "yellow": settings_row.risk_pct_yellow,
        "red": settings_row.risk_pct_red,
    }
    return float(mapping.get(state, settings_row.risk_pct_yellow)), state
