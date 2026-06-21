"""VCP Scanner - Orchestrates batch scanning, alerting, and watchlist cleanup.

Responsibilities:
1. Run VCP scan: fetch data → SEPA filter → VCP detect → persist results
2. Alert logic: state-driven dedup (reset on failure)
3. Watchlist auto-expiry: disable stale auto-seeded entries
4. SEPA seeding: import top stocks from recent screener runs
"""

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd

from db.models import (
    SessionLocal, VcpWatchlist, VcpScanRun, VcpScanResult, VcpAlert,
    ScreenerRun, ScreenerResult,
)
from app.data.yfinance_provider import YFinanceProvider
from app.data.rs_rating import get_rs_snapshot
from app.vcp_monitor.detector import detect_vcp, Contraction
from app.screener.filters import (
    filter_sepa_ma_position, filter_sepa_sma200_trend,
    filter_sepa_52w_low, filter_sepa_52w_high, filter_sepa_rs_rating,
)

logger = logging.getLogger(__name__)
_yf = YFinanceProvider()

# Lock to prevent concurrent VCP scans
_scan_lock = asyncio.Lock()


async def run_vcp_scan(trigger: str = "manual") -> int:
    """Execute a full VCP scan. Returns run_id.

    Flow:
    1. Get enabled watchlist symbols
    2. Batch download 1-year OHLCV
    3. Filter through SEPA conditions
    4. Run VCP detector on passing stocks
    5. Persist results and trigger alerts
    """
    if _scan_lock.locked():
        raise RuntimeError("A VCP scan is already running")

    async with _scan_lock:
        return await _execute_scan(trigger)


async def _execute_scan(trigger: str) -> int:
    """Internal scan execution."""
    db = SessionLocal()

    # Create run record
    run = VcpScanRun(trigger=trigger, status="running")
    db.add(run)
    db.commit()
    run_id = run.id

    try:
        # Step 1: Get watchlist
        watchlist = db.query(VcpWatchlist).filter_by(enabled=True).all()
        symbols = [w.symbol for w in watchlist]
        db.close()

        if not symbols:
            _update_run(run_id, status="completed", total=0, detected=0)
            return run_id

        logger.info(f"VCP scan started: {len(symbols)} symbols, trigger={trigger}")

        # Step 2: Batch download OHLCV
        history_data = await asyncio.to_thread(
            _yf.get_batch_history, symbols, "1y"
        )
        logger.info(f"VCP scan: got OHLCV for {len(history_data)}/{len(symbols)} stocks")

        # Step 3: Get RS snapshot
        rs_snapshot = await asyncio.to_thread(get_rs_snapshot, symbols)

        # Step 4: SEPA filter + VCP detection
        results = []
        detected_count = 0

        for sym in symbols:
            df = history_data.get(sym)
            if df is None or df.empty or len(df) < 200:
                continue

            # Compute SMA indicators needed for SEPA
            df = _compute_sma(df)
            rs = rs_snapshot.get(sym, 0.0)
            info = {"rs_percentile": rs}

            # Apply SEPA filters (all 5 must pass)
            if not _passes_sepa(df, info):
                continue

            # Run VCP detector
            vcp_result = detect_vcp(df, rs_percentile=rs)
            if vcp_result is None:
                continue

            detected_count += 1

            # Serialize contractions
            contractions_data = [
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
            ]

            results.append(VcpScanResult(
                run_id=run_id,
                symbol=sym,
                status=vcp_result.status,
                score=vcp_result.score,
                pivot_price=vcp_result.pivot_price,
                contractions_json=json.dumps(contractions_data),
                volume_dry_ratio=vcp_result.volume_dry_ratio,
                rs_percentile=rs,
            ))

        # Step 5: Persist results
        db = SessionLocal()
        try:
            if results:
                db.bulk_save_objects(results)

            run_record = db.query(VcpScanRun).filter_by(id=run_id).first()
            if run_record:
                run_record.status = "completed"
                run_record.total = len(symbols)
                run_record.detected = detected_count
                run_record.finished_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        # Step 6: Process alerts
        await _process_alerts(run_id)

        # Step 7: Cleanup stale watchlist entries
        _cleanup_stale_watchlist()

        logger.info(f"VCP scan completed: {detected_count}/{len(symbols)} detected")
        return run_id

    except Exception as e:
        logger.error(f"VCP scan failed: {e}", exc_info=True)
        _update_run(run_id, status="failed", error_message=str(e))
        raise


def _compute_sma(df: pd.DataFrame) -> pd.DataFrame:
    """Compute SMA_50, SMA_150, SMA_200 for SEPA filtering."""
    import pandas_ta as ta
    df = df.copy()
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=150, append=True)
    df.ta.sma(length=200, append=True)
    return df


def _passes_sepa(df: pd.DataFrame, info: dict) -> bool:
    """Check if stock passes all 5 SEPA filters with default params."""
    default_params = [
        (filter_sepa_ma_position, {}),
        (filter_sepa_sma200_trend, {"lookback_days": 22}),
        (filter_sepa_52w_low, {"min_pct": 25}),
        (filter_sepa_52w_high, {"max_pct": 25}),
        (filter_sepa_rs_rating, {"min_rs": 70}),
    ]
    for func, params in default_params:
        if not func(df, info, params):
            return False
    return True


async def _process_alerts(run_id: int):
    """Check scan results for breakout signals and create alerts."""
    db = SessionLocal()
    try:
        breakouts = db.query(VcpScanResult).filter_by(
            run_id=run_id, status="breakout"
        ).all()

        for result in breakouts:
            if _should_alert(db, result.symbol, "breakout"):
                # Check if there was a prior failed state
                prior_failed = _had_prior_failure(db, result.symbol)

                alert = VcpAlert(
                    symbol=result.symbol,
                    alert_type="breakout",
                    pivot_price=result.pivot_price,
                    breakout_price=result.pivot_price,  # Will be updated with actual price
                    volume_ratio=result.volume_dry_ratio,
                    prior_failed=prior_failed,
                    sent_feishu=False,
                )
                db.add(alert)

                # Update watchlist last_triggered_at
                wl_item = db.query(VcpWatchlist).filter_by(
                    symbol=result.symbol, enabled=True
                ).first()
                if wl_item:
                    wl_item.last_triggered_at = datetime.now(timezone.utc)

        db.commit()

        # Send Feishu notifications for new alerts
        unsent = db.query(VcpAlert).filter_by(sent_feishu=False).all()
        for alert in unsent:
            await _send_feishu_alert(alert)
            alert.sent_feishu = True
        db.commit()

    except Exception as e:
        logger.error(f"Alert processing error: {e}", exc_info=True)
    finally:
        db.close()


def _should_alert(db, symbol: str, alert_type: str) -> bool:
    """State-driven dedup: allow alert if no recent alert OR if failed in between."""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_alerts = db.query(VcpAlert).filter(
        VcpAlert.symbol == symbol,
        VcpAlert.alert_type == alert_type,
        VcpAlert.alerted_at >= seven_days_ago,
    ).all()

    if not recent_alerts:
        return True

    # Check if there was a failed state since last alert
    last_alert_time = max(a.alerted_at for a in recent_alerts)
    intermediate = db.query(VcpScanResult).filter(
        VcpScanResult.symbol == symbol,
        VcpScanResult.created_at >= last_alert_time,
        VcpScanResult.status == "failed",
    ).first()

    return intermediate is not None  # Reset dedup if failed in between


def _had_prior_failure(db, symbol: str) -> bool:
    """Check if this symbol had a 'failed' status in recent scan results."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    failed = db.query(VcpScanResult).filter(
        VcpScanResult.symbol == symbol,
        VcpScanResult.status == "failed",
        VcpScanResult.created_at >= thirty_days_ago,
    ).first()
    return failed is not None


async def _send_feishu_alert(alert: VcpAlert):
    """Send VCP breakout alert via Feishu."""
    try:
        from app.bot.feishu_client import send_text
        from app.monitor.scheduler import _default_chat_id

        if not _default_chat_id:
            logger.warning("No Feishu chat_id configured, skipping VCP alert")
            return

        msg = (
            f"[VCP突破] {alert.symbol}\n"
            f"放量突破 Pivot ${alert.pivot_price:.2f}\n"
            f"量能干枯比: {alert.volume_ratio:.2f}\n"
            f"{'⚡ 二次突破（经历过回撤失败）' if alert.prior_failed else ''}"
        )
        await send_text(_default_chat_id, msg)
    except Exception as e:
        logger.error(f"Feishu alert send failed: {e}")


def _cleanup_stale_watchlist():
    """Remove stale auto-seeded entries that haven't produced signals."""
    db = SessionLocal()
    try:
        stale_items = db.query(VcpWatchlist).filter_by(
            auto_seeded=True, enabled=True
        ).all()

        ten_days_ago = datetime.now(timezone.utc) - timedelta(days=14)

        for item in stale_items:
            # Skip recently added items
            if item.created_at and item.created_at > ten_days_ago:
                continue

            # Check recent scan results for this symbol
            recent_results = db.query(VcpScanResult).filter(
                VcpScanResult.symbol == item.symbol,
                VcpScanResult.created_at >= ten_days_ago,
            ).all()

            if not recent_results:
                # No results at all (not passing SEPA anymore)
                item.enabled = False
                continue

            # All results are "failed"
            if all(r.status == "failed" for r in recent_results):
                item.enabled = False

        db.commit()
        disabled = sum(1 for i in stale_items if not i.enabled)
        if disabled:
            logger.info(f"VCP watchlist cleanup: disabled {disabled} stale entries")
    except Exception as e:
        logger.error(f"Watchlist cleanup error: {e}")
    finally:
        db.close()


def seed_from_sepa_results(max_items: int = 50) -> int:
    """Import top stocks from the most recent SEPA screener run into VCP watchlist.

    Returns number of newly added symbols.
    """
    db = SessionLocal()
    try:
        # Find latest completed screener run
        latest_run = db.query(ScreenerRun).filter_by(
            status="completed"
        ).order_by(ScreenerRun.id.desc()).first()

        if not latest_run:
            return 0

        # Get passed results sorted by score
        passed = db.query(ScreenerResult).filter_by(
            run_id=latest_run.id, passed=True
        ).order_by(ScreenerResult.score.desc()).limit(max_items).all()

        # Get existing watchlist symbols
        existing = {w.symbol for w in db.query(VcpWatchlist).all()}

        added = 0
        for result in passed:
            if result.symbol not in existing:
                db.add(VcpWatchlist(
                    symbol=result.symbol,
                    source="auto",
                    auto_seeded=True,
                    enabled=True,
                    note=f"From screener run #{latest_run.version}",
                ))
                added += 1

        if added:
            db.commit()
            logger.info(f"VCP seeded {added} stocks from screener run #{latest_run.version}")
        return added
    except Exception as e:
        logger.error(f"SEPA seeding error: {e}")
        return 0
    finally:
        db.close()


def _update_run(run_id: int, **kwargs):
    """Update VCP scan run record."""
    db = SessionLocal()
    try:
        run = db.query(VcpScanRun).filter_by(id=run_id).first()
        if run:
            for k, v in kwargs.items():
                setattr(run, k, v)
            if "status" in kwargs and kwargs["status"] in ("completed", "failed"):
                run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
