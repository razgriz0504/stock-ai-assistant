"""Stock screener engine: orchestrates batch data fetch, filtering, scoring, and persistence."""

import json
import logging
import asyncio
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta

from db.models import SessionLocal, ScreenerRun, ScreenerResult
from app.data.yfinance_provider import YFinanceProvider
from app.data.akshare_provider import AkshareProvider
from app.screener.universe import get_universe
from app.screener.universe_cn import get_universe_cn, get_universe_cn_names
from app.screener.filters import apply_fundamental_filters, apply_technical_filters
from app.analysis.stock_analyzer import calculate_score
from app.data.rs_rating import get_rs_snapshot, compute_rs_snapshot
from app.data.rs_rating_cn import get_rs_snapshot_cn

logger = logging.getLogger(__name__)


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""

    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

_yf_provider = YFinanceProvider()
_ak_provider = AkshareProvider()


def _get_provider(market: str):
    """按 market 返回对应的 DataProvider."""
    if market == "cn":
        return _ak_provider
    return _yf_provider


def _get_universe(market: str) -> list[str]:
    """按 market 返回对应的股票池."""
    if market == "cn":
        return get_universe_cn()
    return get_universe()


def _get_rs_snapshot(market: str, symbols: list[str]) -> dict[str, float]:
    """按 market 返回对应的 RS 快照."""
    if market == "cn":
        return get_rs_snapshot_cn(symbols)
    return get_rs_snapshot(symbols)


# Lock to prevent concurrent screener runs
_running_lock = asyncio.Lock()


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators on a DataFrame (same as StockAnalyzer)."""
    if df.empty or len(df) < 30:
        return df

    for length in [5, 10, 20, 60, 120]:
        df.ta.sma(length=length, append=True)
    # SEPA 所需的长期均线
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=150, append=True)
    df.ta.sma(length=200, append=True)
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=10, append=True)
    df.ta.ema(length=12, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.kdj(length=9, signal=3, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.obv(append=True)
    df['Vol_SMA_5'] = ta.sma(df['Volume'], length=5)
    df['Vol_SMA_20'] = ta.sma(df['Volume'], length=20)
    df['Volume_Ratio'] = df['Volume'] / df['Vol_SMA_20'].replace(0, np.nan)

    return df


def _get_next_version() -> int:
    """Get next screener run version number."""
    db = SessionLocal()
    try:
        last = db.query(ScreenerRun).order_by(ScreenerRun.version.desc()).first()
        return (last.version + 1) if last else 1
    finally:
        db.close()


def _extract_indicators_snapshot(df: pd.DataFrame, info: dict | None = None) -> dict:
    """Extract key indicator values from the last row for display.

    Includes both generic indicators and SEPA-specific metrics.
    """
    if df.empty:
        return {}
    last = df.iloc[-1]
    keys = ["EMA_20", "EMA_50", "SMA_20", "SMA_50", "SMA_150", "SMA_200",
            "MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9",
            "RSI_14", "K_9_3", "D_9_3", "J_9_3",
            "Volume_Ratio", "ATRr_14"]
    snapshot = {}
    for k in keys:
        v = last.get(k)
        if v is not None and not pd.isna(v):
            snapshot[k] = round(float(v), 4)

    # ── SEPA-specific metrics ──
    close = float(last["Close"])

    # 52-week high/low distances
    lookback_252 = min(252, len(df))
    low_52w = float(df["Low"].iloc[-lookback_252:].min())
    high_52w = float(df["High"].iloc[-lookback_252:].max())

    if low_52w > 0:
        snapshot["_52w_low_pct"] = round(((close - low_52w) / low_52w) * 100, 1)
    if high_52w > 0:
        snapshot["_52w_high_pct"] = round(((high_52w - close) / high_52w) * 100, 1)

    # SMA200 slope (linear regression over 22 days)
    sma200_col = "SMA_200"
    if sma200_col in df.columns and len(df) >= 222:
        sma200_series = df[sma200_col].iloc[-22:]
        if not sma200_series.isna().any():
            from scipy import stats as _stats
            x = np.arange(len(sma200_series))
            y = sma200_series.values.astype(float)
            slope, _, _, _, _ = _stats.linregress(x, y)
            # Normalize slope as % per day relative to current SMA200
            sma200_val = float(sma200_series.iloc[-1])
            if sma200_val > 0:
                snapshot["_sma200_slope"] = round((slope / sma200_val) * 100, 4)

    # RS percentile (from info dict, injected by engine)
    if info and "rs_percentile" in info:
        snapshot["_rs_percentile"] = round(float(info["rs_percentile"]), 1)

    return snapshot


async def run_screener(
    filters_config: dict,
    custom_code: str = "",
    trigger: str = "manual",
    preset_id: Optional[int] = None,
    market: str = "us",
) -> int:
    """Run a full screener scan. Returns run_id.

    This function runs in the background and updates progress in the DB.
    """
    if _running_lock.locked():
        raise RuntimeError("A screener scan is already running")

    async with _running_lock:
        return await _execute_screener(filters_config, custom_code, trigger, preset_id, market)


async def _execute_screener(
    filters_config: dict,
    custom_code: str,
    trigger: str,
    preset_id: Optional[int],
    market: str = "us",
) -> int:
    """Internal screener execution logic."""
    version = _get_next_version()

    # Create run record
    db = SessionLocal()
    run = ScreenerRun(
        version=version,
        preset_id=preset_id,
        filters_json=json.dumps(filters_config, ensure_ascii=False),
        custom_code=custom_code,
        trigger=trigger,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()

    try:
        provider = _get_provider(market)

        # Step 1: Get universe
        symbols = await asyncio.to_thread(_get_universe, market)
        _update_run(run_id, total_stocks=len(symbols), progress_pct=5)

        # Step 2: Check if ANY filters are enabled
        has_fundamental_filters = _has_enabled_filters(filters_config, "fundamental")
        has_technical_filters = _has_enabled_filters(filters_config, "technical")
        has_custom_code = bool(custom_code and custom_code.strip())

        logger.info(f"Screener config: fundamental={has_fundamental_filters}, technical={has_technical_filters}, custom={has_custom_code}")

        # Fast path: no filters at all → all stocks pass
        if not has_fundamental_filters and not has_technical_filters and not has_custom_code:
            logger.info("No filters enabled - all stocks pass by default")
            results = []
            for sym in symbols:
                results.append(ScreenerResult(
                    run_id=run_id,
                    symbol=sym,
                    passed=True,
                    score=None,
                    rating="",
                    price=None,
                    change_pct=None,
                    filter_details_json="{}",
                    indicators_json="{}",
                ))
            db = SessionLocal()
            try:
                db.bulk_save_objects(results)
                run_record = db.query(ScreenerRun).filter_by(id=run_id).first()
                if run_record:
                    run_record.status = "completed"
                    run_record.passed_stocks = len(symbols)
                    run_record.total_stocks = len(symbols)
                    run_record.progress_pct = 100
                    run_record.completed_at = datetime.now(timezone.utc)
                db.commit()
            finally:
                db.close()
            logger.info(f"Screener run #{version} completed (no filters): {len(symbols)}/{len(symbols)} passed")
            return run_id

        # Step 3: Fetch fundamental data (parallel, cached)
        fundamentals: dict[str, dict] = {}

        if has_fundamental_filters:
            fundamentals = await asyncio.to_thread(
                provider.get_batch_fundamentals, symbols, 10
            )
            _update_run(run_id, progress_pct=20)

            # Apply fundamental filters first (reduces working set)
            passed_fundamental = []
            for sym in symbols:
                info = fundamentals.get(sym, {})
                passed, _ = apply_fundamental_filters(info, filters_config)
                if passed:
                    passed_fundamental.append(sym)
            symbols_to_scan = passed_fundamental
        else:
            symbols_to_scan = symbols

        _update_run(run_id, progress_pct=25)
        logger.info(f"Screener: {len(symbols_to_scan)} stocks passed fundamental filters (from {len(symbols)} total)")

        # Step 4: Batch download OHLCV for remaining stocks
        need_ohlcv = has_technical_filters or has_custom_code

        history_data: dict[str, pd.DataFrame] = {}
        if need_ohlcv and symbols_to_scan:
            history_data = await asyncio.to_thread(
                provider.get_batch_history, symbols_to_scan, "2y"
            )
            logger.info(f"Screener: got OHLCV data for {len(history_data)}/{len(symbols_to_scan)} stocks")
        _update_run(run_id, progress_pct=60)

        # Step 5: Compute indicators + apply technical filters + score
        results = []
        total = len(symbols_to_scan)
        filter_fail_counts: dict[str, int] = {}  # Track which filter rejects most stocks

        # Pre-compute RS percentile if SEPA RS filter is enabled
        rs_snapshot: dict[str, float] = {}
        technical_config = filters_config.get("technical", {})
        if technical_config.get("sepa_rs_rating", {}).get("enabled", False):
            rs_snapshot = await asyncio.to_thread(
                _get_rs_snapshot, market, symbols_to_scan
            )
            logger.info(f"RS snapshot loaded: {len(rs_snapshot)} stocks")

        for idx, sym in enumerate(symbols_to_scan):
            try:
                info = fundamentals.get(sym, {})
                df = history_data.get(sym, pd.DataFrame())

                # Inject RS percentile into info for SEPA filter
                if rs_snapshot:
                    info["rs_percentile"] = rs_snapshot.get(sym, 0.0)

                filter_details = {}
                passed = True

                # Fundamental filter details (already passed but record them)
                if has_fundamental_filters:
                    _, f_details = apply_fundamental_filters(info, filters_config)
                    filter_details.update(f_details)

                # Technical filters
                if has_technical_filters and not df.empty:
                    df = _compute_indicators(df.copy())
                    t_passed, t_details = apply_technical_filters(df, info, filters_config)
                    filter_details.update(t_details)
                    if not t_passed:
                        passed = False
                        # Track which filter caused the failure (the last False one)
                        for fname, fpassed in t_details.items():
                            if not fpassed:
                                filter_fail_counts[fname] = filter_fail_counts.get(fname, 0) + 1
                                break
                elif has_technical_filters and df.empty:
                    passed = False
                    filter_details["_no_data"] = True
                    filter_fail_counts["_no_data"] = filter_fail_counts.get("_no_data", 0) + 1

                # Custom code filter (skip for now - can be added later)
                # TODO: sandbox execution for custom filter code

                # Score passing stocks
                score = None
                rating = ""
                if passed and not df.empty:
                    if not has_technical_filters:
                        df = _compute_indicators(df.copy())
                    try:
                        score_val, _ = calculate_score(df)
                        score = round(score_val, 2)
                        if score >= 4.5:
                            rating = "AA"
                        elif score >= 4.0:
                            rating = "A"
                        elif score >= 3.0:
                            rating = "B"
                        elif score >= 2.0:
                            rating = "C"
                        else:
                            rating = "D"
                    except Exception:
                        pass

                # Get price info
                price = None
                change_pct = None
                if not df.empty:
                    last_row = df.iloc[-1]
                    price = round(float(last_row["Close"]), 2)
                    if len(df) >= 2:
                        prev_close = float(df.iloc[-2]["Close"])
                        if prev_close > 0:
                            change_pct = round((float(last_row["Close"]) - prev_close) / prev_close * 100, 2)

                indicators_snapshot = _extract_indicators_snapshot(df, info) if not df.empty else {}

                # Add name and sector to snapshot for display
                indicators_snapshot["_name"] = info.get("short_name", "")
                indicators_snapshot["_sector"] = info.get("sector", "")
                indicators_snapshot["_industry"] = info.get("industry", "")

                results.append(ScreenerResult(
                    run_id=run_id,
                    symbol=sym,
                    passed=passed,
                    score=score,
                    rating=rating,
                    price=price,
                    change_pct=change_pct,
                    market_cap=info.get("market_cap"),
                    pe_ratio=info.get("pe_ratio"),
                    revenue_growth=info.get("revenue_growth"),
                    roe=info.get("roe"),
                    dividend_yield=info.get("dividend_yield"),
                    filter_details_json=json.dumps(filter_details, cls=_NumpyEncoder),
                    indicators_json=json.dumps(indicators_snapshot, cls=_NumpyEncoder),
                ))
            except Exception as e:
                logger.warning(f"Screener error for {sym}: {e}")
                results.append(ScreenerResult(
                    run_id=run_id,
                    symbol=sym,
                    passed=False,
                    filter_details_json=json.dumps({"_error": str(e)}),
                ))

            # Update progress periodically
            if (idx + 1) % 20 == 0 or idx == total - 1:
                pct = 60 + int((idx + 1) / total * 35)
                _update_run(run_id, progress_pct=min(pct, 95))

        # Step 6: Fetch name/sector for passed stocks if fundamentals weren't loaded
        if not has_fundamental_filters:
            passed_symbols = [r.symbol for r in results if r.passed]
            if passed_symbols:
                logger.info(f"Fetching fundamentals for {len(passed_symbols)} passed stocks...")
                extra_fundamentals = await asyncio.to_thread(
                    provider.get_batch_fundamentals, passed_symbols, 10
                )
                # Update indicators_json with name/sector
                for r in results:
                    if r.passed and r.symbol in extra_fundamentals:
                        info = extra_fundamentals[r.symbol]
                        snapshot = json.loads(r.indicators_json) if r.indicators_json else {}
                        snapshot["_name"] = info.get("short_name", "")
                        snapshot["_sector"] = info.get("sector", "")
                        snapshot["_industry"] = info.get("industry", "")
                        r.indicators_json = json.dumps(snapshot, cls=_NumpyEncoder)
                        # Also fill in fundamental fields
                        if not r.market_cap:
                            r.market_cap = info.get("market_cap")
                        if not r.pe_ratio:
                            r.pe_ratio = info.get("pe_ratio")
                        if not r.revenue_growth:
                            r.revenue_growth = info.get("revenue_growth")
                        if not r.roe:
                            r.roe = info.get("roe")
                        if not r.dividend_yield:
                            r.dividend_yield = info.get("dividend_yield")

        # Step 7: Persist results
        if filter_fail_counts:
            logger.info(f"Screener filter rejection breakdown: {filter_fail_counts}")
        no_data_count = sum(1 for r in results if r.filter_details_json and "_no_data" in r.filter_details_json)
        error_count = sum(1 for r in results if r.filter_details_json and "_error" in r.filter_details_json)
        if no_data_count > 0 or error_count > 0:
            logger.warning(f"Screener issues: {no_data_count} stocks had no OHLCV data, {error_count} had errors")

        db = SessionLocal()
        try:
            db.bulk_save_objects(results)
            passed_count = sum(1 for r in results if r.passed)
            run_record = db.query(ScreenerRun).filter_by(id=run_id).first()
            if run_record:
                run_record.status = "completed"
                run_record.passed_stocks = passed_count
                run_record.total_stocks = len(symbols)
                run_record.progress_pct = 100
                run_record.completed_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        logger.info(f"Screener run #{version} completed: {passed_count}/{len(symbols)} passed")
        return run_id

    except Exception as e:
        logger.error(f"Screener run failed: {e}")
        _update_run(run_id, status="failed", error_message=str(e))
        raise


def _update_run(run_id: int, **kwargs):
    """Update screener run record."""
    db = SessionLocal()
    try:
        run = db.query(ScreenerRun).filter_by(id=run_id).first()
        if run:
            for k, v in kwargs.items():
                setattr(run, k, v)
            db.commit()
    finally:
        db.close()


def _has_enabled_filters(filters_config: dict, category: str) -> bool:
    """Check if any filter in a category is enabled."""
    cat_config = filters_config.get(category, {})
    return any(v.get("enabled", False) for v in cat_config.values() if isinstance(v, dict))
