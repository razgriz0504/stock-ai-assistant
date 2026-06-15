"""Stock Screener REST API（前端 SPA: ScreenerPage.tsx）"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from db.models import (
    SessionLocal, ScreenerPreset, ScreenerRun, ScreenerResult, ScreenerConfig
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════

class RunRequest(BaseModel):
    filters: dict = {}
    custom_code: str = ""
    preset_id: Optional[int] = None


class PresetRequest(BaseModel):
    id: Optional[int] = None
    name: str
    filters_json: str = "{}"
    custom_code: str = ""
    is_default: bool = False


class ScheduleRequest(BaseModel):
    schedule_enabled: bool = False
    schedule_frequency: str = "daily"
    schedule_day_of_week: str = "mon-fri"
    schedule_hour: int = 16
    schedule_minute: int = 30
    schedule_preset_id: Optional[int] = None


# ═══════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════

@router.post("/api/screener/run")
async def start_screener(req: RunRequest, background_tasks: BackgroundTasks):
    """Start a screener scan (async background task)."""
    from app.screener.engine import run_screener, _running_lock

    if _running_lock.locked():
        raise HTTPException(status_code=409, detail="A screener scan is already running")

    # Create task
    async def _run():
        try:
            await run_screener(
                filters_config=req.filters,
                custom_code=req.custom_code,
                trigger="manual",
                preset_id=req.preset_id,
            )
        except Exception as e:
            logger.error(f"Background screener failed: {e}")

    # Run in background
    loop = asyncio.get_event_loop()
    loop.create_task(_run())

    # Return the latest run_id (just created)
    await asyncio.sleep(0.3)  # Brief wait for record creation
    db = SessionLocal()
    try:
        run = db.query(ScreenerRun).order_by(ScreenerRun.id.desc()).first()
        return {"run_id": run.id if run else 0, "status": "running"}
    finally:
        db.close()


@router.get("/api/screener/status/{run_id}")
async def get_status(run_id: int):
    """Get screener run status and progress."""
    db = SessionLocal()
    try:
        run = db.query(ScreenerRun).filter_by(id=run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return {
            "run_id": run.id,
            "version": run.version,
            "status": run.status,
            "progress_pct": run.progress_pct,
            "total_stocks": run.total_stocks,
            "passed_stocks": run.passed_stocks,
            "error_message": run.error_message,
        }
    finally:
        db.close()


@router.get("/api/screener/results/{run_id}")
async def get_results(run_id: int, sort_by: str = "score", order: str = "desc"):
    """Get screener results for a run (only passed stocks)."""
    db = SessionLocal()
    try:
        results = db.query(ScreenerResult).filter_by(run_id=run_id, passed=True).all()
        data = []
        for r in results:
            indicators = json.loads(r.indicators_json) if r.indicators_json else {}
            data.append({
                "symbol": r.symbol,
                "name": indicators.get("_name", ""),
                "sector": indicators.get("_sector", ""),
                "industry": indicators.get("_industry", ""),
                "score": r.score,
                "rating": r.rating,
                "price": r.price,
                "change_pct": r.change_pct,
                "market_cap": r.market_cap,
                "pe_ratio": r.pe_ratio,
                "revenue_growth": r.revenue_growth,
                "roe": r.roe,
                "dividend_yield": r.dividend_yield,
                "filter_details": json.loads(r.filter_details_json) if r.filter_details_json else {},
                "indicators": indicators,
            })

        # Sort
        reverse = (order == "desc")
        if sort_by in ("score", "price", "change_pct", "market_cap", "pe_ratio", "revenue_growth", "roe"):
            data.sort(key=lambda x: x.get(sort_by) or 0, reverse=reverse)
        else:
            data.sort(key=lambda x: x.get("score") or 0, reverse=True)

        return {"run_id": run_id, "total_passed": len(data), "results": data}
    finally:
        db.close()


@router.get("/api/screener/runs")
async def list_runs():
    """List recent screener runs."""
    db = SessionLocal()
    try:
        runs = db.query(ScreenerRun).order_by(ScreenerRun.id.desc()).limit(20).all()
        return [
            {
                "id": r.id,
                "version": r.version,
                "trigger": r.trigger,
                "status": r.status,
                "total_stocks": r.total_stocks,
                "passed_stocks": r.passed_stocks,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in runs
        ]
    finally:
        db.close()


@router.get("/api/screener/chart/{symbol}")
async def get_chart(symbol: str, period: str = "6mo"):
    """Generate on-demand chart for a symbol (base64 PNG)."""
    import io
    import base64
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplfinance as mpf
    from app.data.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    df = provider.get_history(symbol.upper(), period)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    # Create chart
    buf = io.BytesIO()
    kwargs = dict(
        type="candle",
        style="charles",
        volume=True,
        title=f"{symbol.upper()} ({period})",
        figsize=(10, 6),
        savefig=dict(fname=buf, dpi=100, bbox_inches="tight"),
    )

    # Add moving averages if enough data
    if len(df) > 20:
        kwargs["mav"] = (5, 20)

    mpf.plot(df, **kwargs)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close("all")

    return {"symbol": symbol.upper(), "chart_base64": f"data:image/png;base64,{b64}"}


# ── Presets CRUD ──

@router.get("/api/screener/presets")
async def list_presets():
    db = SessionLocal()
    try:
        presets = db.query(ScreenerPreset).order_by(ScreenerPreset.name).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "filters_json": p.filters_json,
                "custom_code": p.custom_code,
                "is_default": p.is_default,
            }
            for p in presets
        ]
    finally:
        db.close()


@router.post("/api/screener/presets")
async def save_preset(req: PresetRequest):
    db = SessionLocal()
    try:
        if req.id:
            p = db.query(ScreenerPreset).filter_by(id=req.id).first()
            if p:
                p.name = req.name
                p.filters_json = req.filters_json
                p.custom_code = req.custom_code
                p.is_default = req.is_default
        else:
            p = ScreenerPreset(
                name=req.name,
                filters_json=req.filters_json,
                custom_code=req.custom_code,
                is_default=req.is_default,
            )
            db.add(p)
        db.commit()
        return {"success": True, "id": p.id}
    finally:
        db.close()


@router.delete("/api/screener/presets/{preset_id}")
async def delete_preset(preset_id: int):
    db = SessionLocal()
    try:
        p = db.query(ScreenerPreset).filter_by(id=preset_id).first()
        if p:
            db.delete(p)
            db.commit()
        return {"success": True}
    finally:
        db.close()


# ── Schedule ──

@router.get("/api/screener/schedule")
async def get_schedule():
    db = SessionLocal()
    try:
        cfg = db.query(ScreenerConfig).filter_by(id=1).first()
        if not cfg:
            return {"schedule_enabled": False, "schedule_frequency": "daily",
                    "schedule_day_of_week": "mon-fri", "schedule_hour": 16,
                    "schedule_minute": 30, "schedule_preset_id": None}
        return {
            "schedule_enabled": cfg.schedule_enabled,
            "schedule_frequency": cfg.schedule_frequency,
            "schedule_day_of_week": cfg.schedule_day_of_week,
            "schedule_hour": cfg.schedule_hour,
            "schedule_minute": cfg.schedule_minute,
            "schedule_preset_id": cfg.schedule_preset_id,
        }
    finally:
        db.close()


@router.post("/api/screener/schedule")
async def update_schedule(req: ScheduleRequest):
    db = SessionLocal()
    try:
        cfg = db.query(ScreenerConfig).filter_by(id=1).first()
        if not cfg:
            cfg = ScreenerConfig(id=1)
            db.add(cfg)
        cfg.schedule_enabled = req.schedule_enabled
        cfg.schedule_frequency = req.schedule_frequency
        cfg.schedule_day_of_week = req.schedule_day_of_week
        cfg.schedule_hour = req.schedule_hour
        cfg.schedule_minute = req.schedule_minute
        cfg.schedule_preset_id = req.schedule_preset_id
        db.commit()

        # Update scheduler
        from app.monitor.scheduler import update_screener_schedule
        update_screener_schedule(cfg)

        return {"success": True}
    finally:
        db.close()
