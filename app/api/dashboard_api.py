"""Dashboard 聚合接口 - 把首页变成晨会简报

聚合多个数据源给前端工作台首页一次性返回:
- 板块强度:Top3 涨幅 / Top3 跌幅 / 资金流入流出
- 选股器:最近 24h run、最新一次通过股
- 关注列表:数量与列表
- X 舆情:近 24h 数量、情绪分布、热议标的
- 周报:最新版本与日期
- 用户提醒:最近一周需要关注的事件
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from db.models import (
    SessionLocal,
    ScreenerRun,
    ScreenerResult,
    User,
    UserPreference,
    WeeklyReport,
    XTweet,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

WEB_USER_ID = "web_default"  # 兼容旧飞书 bot 数据


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ═══════════════════════════════════════════════════════════════
# 子查询函数 - 全部容错,任一失败不影响整体
# ═══════════════════════════════════════════════════════════════


def _watchlist_block(db, user_id: int) -> dict[str, Any]:
    try:
        pref = (
            db.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .first()
        )
        raw = json.loads(pref.watchlist) if pref and pref.watchlist else []
        # 兼容旧(字符串) + 新(对象) 两种格式
        symbols: list[str] = []
        for x in raw if isinstance(raw, list) else []:
            if isinstance(x, str):
                s = x.strip().upper()
            elif isinstance(x, dict):
                s = str(x.get("symbol", "")).strip().upper()
            else:
                s = ""
            if s:
                symbols.append(s)
        return {"count": len(symbols), "stocks": symbols[:30]}
    except Exception as e:
        logger.warning(f"[dashboard] watchlist block failed: {e}")
        return {"count": 0, "stocks": []}


def _screener_block(db) -> dict[str, Any]:
    """最新一次成功 run + 最近 24h run 数量"""
    try:
        latest = (
            db.query(ScreenerRun)
            .order_by(ScreenerRun.id.desc())
            .first()
        )
        latest_completed = (
            db.query(ScreenerRun)
            .filter(ScreenerRun.status == "completed")
            .order_by(ScreenerRun.id.desc())
            .first()
        )
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_count = (
            db.query(ScreenerRun)
            .filter(ScreenerRun.started_at >= cutoff)
            .count()
        )

        top_stocks: list[dict[str, Any]] = []
        if latest_completed:
            results = (
                db.query(ScreenerResult)
                .filter_by(run_id=latest_completed.id, passed=True)
                .all()
            )
            data = []
            for r in results:
                ind = json.loads(r.indicators_json) if r.indicators_json else {}
                data.append(
                    {
                        "symbol": r.symbol,
                        "name": ind.get("_name", ""),
                        "sector": ind.get("_sector", ""),
                        "score": r.score,
                        "rating": r.rating,
                        "price": r.price,
                        "change_pct": r.change_pct,
                    }
                )
            data.sort(key=lambda x: x.get("score") or 0, reverse=True)
            top_stocks = data[:5]

        return {
            "recent_24h_runs": recent_count,
            "latest": {
                "id": latest.id,
                "status": latest.status,
                "trigger": latest.trigger,
                "passed_stocks": latest.passed_stocks or 0,
                "total_stocks": latest.total_stocks or 0,
                "started_at": _iso(latest.started_at),
            }
            if latest
            else None,
            "latest_completed_id": latest_completed.id if latest_completed else None,
            "top_stocks": top_stocks,
        }
    except Exception as e:
        logger.warning(f"[dashboard] screener block failed: {e}")
        return {
            "recent_24h_runs": 0,
            "latest": None,
            "latest_completed_id": None,
            "top_stocks": [],
        }


def _report_block(db) -> dict[str, Any]:
    try:
        latest = (
            db.query(WeeklyReport)
            .filter(WeeklyReport.status == "completed")
            .order_by(WeeklyReport.version.desc())
            .first()
        )
        running = (
            db.query(WeeklyReport)
            .filter(WeeklyReport.status == "running")
            .first()
        )
        if not latest:
            return {"latest": None, "is_running": running is not None}
        return {
            "latest": {
                "id": latest.id,
                "version": latest.version,
                "report_date": _iso(latest.report_date),
                "model_name": latest.model_name or "",
                "trigger": latest.trigger,
            },
            "is_running": running is not None,
        }
    except Exception as e:
        logger.warning(f"[dashboard] report block failed: {e}")
        return {"latest": None, "is_running": False}


def _x_monitor_block(db) -> dict[str, Any]:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        tweets = (
            db.query(XTweet)
            .filter(XTweet.created_at_x >= cutoff)
            .all()
        )
        sentiments = {"bullish": 0, "bearish": 0, "neutral": 0}
        asset_count: dict[str, int] = {}
        latest_tweet: dict[str, Any] | None = None

        for t in tweets:
            s = (t.sentiment or "neutral").lower()
            if s in sentiments:
                sentiments[s] += 1
            else:
                sentiments["neutral"] += 1
            try:
                assets = json.loads(t.impact_assets) if t.impact_assets else []
                for a in assets:
                    asset_count[a] = asset_count.get(a, 0) + 1
            except Exception:
                pass
            if latest_tweet is None or (
                t.created_at_x and t.created_at_x > datetime.fromisoformat(latest_tweet["created_at"])
            ):
                latest_tweet = {
                    "username": t.username,
                    "text_zh": t.text_zh or "",
                    "text": t.text or "",
                    "sentiment": s,
                    "created_at": _iso(t.created_at_x) or "",
                }

        top_assets = sorted(
            ({"ticker": k, "count": v} for k, v in asset_count.items()),
            key=lambda x: x["count"],
            reverse=True,
        )[:8]

        return {
            "total_24h": len(tweets),
            "sentiment_distribution": sentiments,
            "top_assets": top_assets,
            "latest_tweet": latest_tweet,
        }
    except Exception as e:
        logger.warning(f"[dashboard] x_monitor block failed: {e}")
        return {
            "total_24h": 0,
            "sentiment_distribution": {"bullish": 0, "bearish": 0, "neutral": 0},
            "top_assets": [],
            "latest_tweet": None,
        }


async def _sector_block() -> dict[str, Any]:
    """板块强度 Top3 / Bottom3 / 资金流入流出 - 走缓存,失败返回空"""
    try:
        from app.data.sector_strength import fetch_enhanced_sector_data

        data = await asyncio.to_thread(fetch_enhanced_sector_data, use_cache=True)
        if not data or "sectors" not in data:
            return {
                "generated_at": None,
                "benchmark": None,
                "top_gainers": [],
                "top_losers": [],
                "inflow": [],
                "outflow": [],
            }

        sectors = data.get("sectors", [])
        # 用 5d 涨幅排序作为今日聚焦,缺省值置底
        with_chg = [s for s in sectors if s.get("chg_5d") is not None]

        def _short(s: dict) -> dict:
            return {
                "symbol": s.get("symbol"),
                "name": s.get("name"),
                "current": s.get("current"),
                "chg_5d": s.get("chg_5d"),
                "chg_30d": s.get("chg_30d"),
                "rs_composite": (s.get("rs") or {}).get("composite"),
                "flow_direction": (s.get("flow") or {}).get("direction"),
            }

        top_gainers = sorted(with_chg, key=lambda x: x.get("chg_5d") or 0, reverse=True)[:3]
        top_losers = sorted(with_chg, key=lambda x: x.get("chg_5d") or 0)[:3]

        inflow = [
            s for s in sectors if (s.get("flow") or {}).get("direction") in ("strong_inflow", "inflow")
        ][:6]
        outflow = [
            s for s in sectors if (s.get("flow") or {}).get("direction") in ("strong_outflow", "outflow")
        ][:6]

        return {
            "generated_at": data.get("generated_at"),
            "benchmark": data.get("benchmark"),
            "top_gainers": [_short(s) for s in top_gainers],
            "top_losers": [_short(s) for s in top_losers],
            "inflow": [_short(s) for s in inflow],
            "outflow": [_short(s) for s in outflow],
        }
    except Exception as e:
        logger.warning(f"[dashboard] sector block failed: {e}")
        return {
            "generated_at": None,
            "benchmark": None,
            "top_gainers": [],
            "top_losers": [],
            "inflow": [],
            "outflow": [],
        }


# ═══════════════════════════════════════════════════════════════
# 提醒列表 - 由前端做样式渲染,后端只产事件元数据
# ═══════════════════════════════════════════════════════════════


def _build_alerts(
    screener: dict[str, Any],
    report: dict[str, Any],
    x_monitor: dict[str, Any],
    sector: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    # 周报状态
    if report.get("is_running"):
        alerts.append(
            {
                "type": "report",
                "level": "info",
                "title": "周报正在生成中",
                "desc": "AI 正在汇总本周市场观点,预计稍后可用",
                "link": "/report-admin",
            }
        )
    elif report.get("latest"):
        report_date = report["latest"].get("report_date")
        if report_date:
            try:
                rd = datetime.fromisoformat(report_date.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - rd).days
                if age_days >= 8:
                    alerts.append(
                        {
                            "type": "report",
                            "level": "warn",
                            "title": f"最新周报已 {age_days} 天未更新",
                            "desc": f"v{report['latest']['version']} · 建议生成新周报",
                            "link": "/report-admin",
                        }
                    )
            except Exception:
                pass

    # 选股器活跃
    latest = screener.get("latest")
    if latest and latest.get("status") == "running":
        alerts.append(
            {
                "type": "screener",
                "level": "info",
                "title": "选股器正在运行",
                "desc": f"已扫描 {latest.get('total_stocks') or 0} 只 · 通过 {latest.get('passed_stocks') or 0} 只",
                "link": "/screener",
            }
        )

    # X 舆情极端值
    sd = x_monitor.get("sentiment_distribution") or {}
    bull = sd.get("bullish", 0)
    bear = sd.get("bearish", 0)
    total = bull + bear + sd.get("neutral", 0)
    if total >= 5:
        if bear >= max(2 * bull, 5):
            alerts.append(
                {
                    "type": "x_monitor",
                    "level": "warn",
                    "title": "近 24h X 舆情明显偏空",
                    "desc": f"看空 {bear} · 看多 {bull} · 总 {total}",
                    "link": "/x-monitor",
                }
            )
        elif bull >= max(2 * bear, 5):
            alerts.append(
                {
                    "type": "x_monitor",
                    "level": "success",
                    "title": "近 24h X 舆情明显偏多",
                    "desc": f"看多 {bull} · 看空 {bear} · 总 {total}",
                    "link": "/x-monitor",
                }
            )

    # 板块异动
    losers = sector.get("top_losers") or []
    if losers and losers[0].get("chg_5d") is not None and losers[0]["chg_5d"] <= -3:
        s = losers[0]
        alerts.append(
            {
                "type": "sector",
                "level": "warn",
                "title": f"板块走弱:{s.get('name')}({s.get('symbol')})",
                "desc": f"近 5 日 {s['chg_5d']:.2f}% · 关注资金流向",
                "link": "/sector-strength",
            }
        )
    gainers = sector.get("top_gainers") or []
    if gainers and gainers[0].get("chg_5d") is not None and gainers[0]["chg_5d"] >= 3:
        s = gainers[0]
        alerts.append(
            {
                "type": "sector",
                "level": "success",
                "title": f"板块走强:{s.get('name')}({s.get('symbol')})",
                "desc": f"近 5 日 +{s['chg_5d']:.2f}% · 关注后续延续",
                "link": "/sector-strength",
            }
        )

    return alerts


# ═══════════════════════════════════════════════════════════════
# 主接口
# ═══════════════════════════════════════════════════════════════


@router.get("/api/dashboard/summary")
async def dashboard_summary(current_user: User = Depends(get_current_user)):
    """聚合首页所有展示数据 - 一次请求拿全"""
    db = SessionLocal()
    try:
        # 同步部分(读 SQLite)
        watchlist = _watchlist_block(db, current_user.id)
        screener = _screener_block(db)
        report = _report_block(db)
        x_monitor = _x_monitor_block(db)
    finally:
        db.close()

    # 异步部分(可能需要拉数据)
    sector = await _sector_block()

    alerts = _build_alerts(screener, report, x_monitor, sector)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "watchlist": watchlist,
        "screener": screener,
        "report": report,
        "x_monitor": x_monitor,
        "sector": sector,
        "alerts": alerts,
    }
