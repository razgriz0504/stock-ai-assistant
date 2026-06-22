"""VCP Monitor API endpoints.

Provides REST API for VCP monitoring features:
- Watchlist CRUD
- Scan triggering and status
- Results and detail views
- Alert history
- SEPA seeding
"""

import json
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.models import (
    SessionLocal, VcpWatchlist, VcpScanRun, VcpScanResult, VcpAlert,
    ScreenerResult,
)
from app.vcp_monitor.scanner import run_vcp_scan, seed_from_sepa_results
from app.vcp_monitor.detector import detect_vcp
from app.data.yfinance_provider import YFinanceProvider
from app.data.rs_rating import get_rs_snapshot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vcp-monitor", tags=["vcp-monitor"])
_yf = YFinanceProvider()


# ── Request/Response Models ──

class WatchlistAddRequest(BaseModel):
    symbol: str
    note: str = ""


class ScanResponse(BaseModel):
    run_id: int
    status: str


# ── Watchlist Endpoints ──

@router.get("/watchlist")
def get_watchlist():
    """Get all VCP watchlist entries."""
    db = SessionLocal()
    try:
        items = db.query(VcpWatchlist).order_by(VcpWatchlist.created_at.desc()).all()
        return [
            {
                "id": item.id,
                "symbol": item.symbol,
                "source": item.source,
                "auto_seeded": item.auto_seeded,
                "enabled": item.enabled,
                "note": item.note,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "last_triggered_at": item.last_triggered_at.isoformat() if item.last_triggered_at else None,
            }
            for item in items
        ]
    finally:
        db.close()


@router.post("/watchlist")
def add_to_watchlist(req: WatchlistAddRequest):
    """Add a symbol to VCP watchlist."""
    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(400, "Symbol is required")

    db = SessionLocal()
    try:
        # Check if already exists
        existing = db.query(VcpWatchlist).filter_by(symbol=symbol).first()
        if existing:
            if not existing.enabled:
                existing.enabled = True
                existing.note = req.note or existing.note
                db.commit()
                return {"message": f"{symbol} re-enabled", "id": existing.id}
            raise HTTPException(409, f"{symbol} already in watchlist")

        item = VcpWatchlist(
            symbol=symbol,
            source="manual",
            auto_seeded=False,
            enabled=True,
            note=req.note,
        )
        db.add(item)
        db.commit()
        return {"message": f"{symbol} added", "id": item.id}
    finally:
        db.close()


@router.delete("/watchlist/{item_id}")
def remove_from_watchlist(item_id: int):
    """Remove (disable) a watchlist entry."""
    db = SessionLocal()
    try:
        item = db.query(VcpWatchlist).filter_by(id=item_id).first()
        if not item:
            raise HTTPException(404, "Item not found")
        item.enabled = False
        db.commit()
        return {"message": f"{item.symbol} disabled"}
    finally:
        db.close()


# ── Scan Endpoints ──

@router.post("/scan")
async def trigger_scan():
    """Trigger a manual VCP scan."""
    try:
        run_id = await run_vcp_scan(trigger="manual")
        return {"run_id": run_id, "status": "completed"}
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(500, f"Scan failed: {e}")


@router.get("/runs")
def get_scan_runs(limit: int = 20):
    """Get VCP scan run history."""
    db = SessionLocal()
    try:
        runs = db.query(VcpScanRun).order_by(
            VcpScanRun.id.desc()
        ).limit(limit).all()
        return [
            {
                "id": r.id,
                "trigger": r.trigger,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "total": r.total,
                "detected": r.detected,
            }
            for r in runs
        ]
    finally:
        db.close()


@router.get("/results/{run_id}")
def get_scan_results(run_id: int):
    """Get results for a specific scan run."""
    db = SessionLocal()
    try:
        results = db.query(VcpScanResult).filter_by(run_id=run_id).order_by(
            VcpScanResult.score.desc()
        ).all()

        # Batch lookup sector info from latest ScreenerResult for each symbol
        symbols = [r.symbol for r in results]
        sector_map: dict[str, str] = {}
        if symbols:
            from sqlalchemy import func
            # Get latest screener result for each symbol that has indicators
            subq = (
                db.query(
                    ScreenerResult.symbol,
                    func.max(ScreenerResult.id).label("max_id")
                )
                .filter(ScreenerResult.symbol.in_(symbols), ScreenerResult.passed == True)
                .group_by(ScreenerResult.symbol)
                .subquery()
            )
            rows = (
                db.query(ScreenerResult.symbol, ScreenerResult.indicators_json)
                .join(subq, ScreenerResult.id == subq.c.max_id)
                .all()
            )
            for sym, ind_json in rows:
                try:
                    ind = json.loads(ind_json) if ind_json else {}
                    sector_map[sym] = ind.get("_sector", "")
                except Exception:
                    pass

        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "status": r.status,
                "score": r.score,
                "pivot_price": r.pivot_price,
                "contractions": json.loads(r.contractions_json) if r.contractions_json else [],
                "volume_dry_ratio": r.volume_dry_ratio,
                "rs_percentile": r.rs_percentile,
                "sector": sector_map.get(r.symbol, ""),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]
    finally:
        db.close()


@router.get("/detail/{symbol}")
async def get_symbol_detail(symbol: str):
    """Get OHLCV + VCP annotation data for charting.

    Returns the data contract for frontend ECharts rendering.
    """
    symbol = symbol.upper().strip()

    # Fetch 1-year OHLCV
    df = await asyncio.to_thread(_yf.get_history, symbol, "1y")
    if df.empty:
        raise HTTPException(404, f"No data for {symbol}")

    # Compute SMAs
    import pandas_ta as ta
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=150, append=True)
    df.ta.sma(length=200, append=True)

    # Get RS
    rs_snapshot = get_rs_snapshot([symbol])
    rs = rs_snapshot.get(symbol, 0.0)

    # Run VCP detection
    vcp_result = detect_vcp(df, rs_percentile=rs)

    # Build OHLCV array
    ohlcv = []
    sma50_arr = []
    sma150_arr = []
    sma200_arr = []

    for idx, row in df.iterrows():
        date_str = str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10]
        ohlcv.append({
            "date": date_str,
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })
        sma50_arr.append(round(float(row.get("SMA_50", 0) or 0), 2))
        sma150_arr.append(round(float(row.get("SMA_150", 0) or 0), 2))
        sma200_arr.append(round(float(row.get("SMA_200", 0) or 0), 2))

    # Build response
    response = {
        "symbol": symbol,
        "ohlcv": ohlcv,
        "sma50": sma50_arr,
        "sma150": sma150_arr,
        "sma200": sma200_arr,
        "rs_percentile": round(rs, 2),
        "volume_sma20": round(float(df["Volume"].iloc[-20:].mean()), 0) if len(df) >= 20 else 0,
    }

    if vcp_result:
        response.update({
            "pivot_price": vcp_result.pivot_price,
            "base_start_date": vcp_result.base_start_date,
            "status": vcp_result.status,
            "score": vcp_result.score,
            "contractions": [
                {
                    "name": c.name,
                    "start_date": c.start_date,
                    "end_date": c.end_date,
                    "high": c.high,
                    "low": c.low,
                    "depth_pct": c.depth_pct,
                    "avg_volume": c.avg_volume,
                }
                for c in vcp_result.contractions
            ],
        })
    else:
        response.update({
            "pivot_price": None,
            "base_start_date": None,
            "status": "none",
            "score": 0,
            "contractions": [],
        })

    return response


# ── Alert Endpoints ──

@router.get("/alerts")
def get_alerts(limit: int = 50):
    """Get VCP alert history."""
    db = SessionLocal()
    try:
        alerts = db.query(VcpAlert).order_by(
            VcpAlert.alerted_at.desc()
        ).limit(limit).all()
        return [
            {
                "id": a.id,
                "symbol": a.symbol,
                "alert_type": a.alert_type,
                "pivot_price": a.pivot_price,
                "breakout_price": a.breakout_price,
                "volume_ratio": a.volume_ratio,
                "prior_failed": a.prior_failed,
                "sent_feishu": a.sent_feishu,
                "alerted_at": a.alerted_at.isoformat() if a.alerted_at else None,
            }
            for a in alerts
        ]
    finally:
        db.close()


# ── Seeding ──

@router.post("/seed-from-sepa")
def seed_watchlist_from_sepa():
    """Seed VCP watchlist from the most recent SEPA screener results."""
    added = seed_from_sepa_results(max_items=50)
    return {"message": f"Seeded {added} stocks from latest SEPA results", "added": added}
