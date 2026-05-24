"""Stock Screener page: API endpoints + inline HTML frontend."""

import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
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
            data.append({
                "symbol": r.symbol,
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
                "indicators": json.loads(r.indicators_json) if r.indicators_json else {},
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


# ═══════════════════════════════════════════════════════════════
# HTML Page
# ═══════════════════════════════════════════════════════════════

@router.get("/screener", response_class=HTMLResponse)
async def screener_page():
    return _build_html()


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Screener - 美股选股器</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0f1923; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; min-height:100vh; }
a { color:#4fc3f7; text-decoration:none; }
button { cursor:pointer; border:none; border-radius:6px; font-size:14px; padding:8px 16px; transition:all .2s; }
input,select { background:#1a2634; border:1px solid #2a3a4a; color:#e0e0e0; padding:6px 10px; border-radius:4px; font-size:13px; }
input:focus,select:focus { outline:none; border-color:#4fc3f7; }

.header { display:flex; align-items:center; justify-content:space-between; padding:16px 24px; border-bottom:1px solid #2a3a4a; background:#1a2634; }
.header h1 { font-size:20px; font-weight:600; }
.header .actions { display:flex; gap:10px; align-items:center; }
.btn-primary { background:#4fc3f7; color:#0f1923; font-weight:600; }
.btn-primary:hover { background:#81d4fa; }
.btn-secondary { background:#2a3a4a; color:#e0e0e0; }
.btn-secondary:hover { background:#3a4a5a; }
.btn-danger { background:#ef5350; color:#fff; }

.layout { display:flex; height:calc(100vh - 65px); }
.sidebar { width:300px; min-width:300px; border-right:1px solid #2a3a4a; overflow-y:auto; padding:16px; }
.main { flex:1; overflow-y:auto; padding:20px; }

.filter-section { margin-bottom:16px; }
.filter-section summary { cursor:pointer; font-weight:600; font-size:14px; color:#4fc3f7; padding:8px 0; user-select:none; }
.filter-item { display:flex; align-items:center; gap:8px; padding:6px 0; font-size:13px; }
.filter-item label { flex:1; cursor:pointer; }
.filter-params { margin-left:26px; padding:4px 0; display:flex; gap:6px; flex-wrap:wrap; }
.filter-params input { width:60px; }
.filter-params select { width:90px; }

.progress-bar { background:#1a2634; border-radius:8px; height:32px; margin-bottom:16px; position:relative; overflow:hidden; border:1px solid #2a3a4a; display:none; }
.progress-bar.active { display:block; }
.progress-fill { height:100%; background:linear-gradient(90deg,#4fc3f7,#29b6f6); border-radius:8px; transition:width .3s; }
.progress-text { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); font-size:13px; font-weight:600; }

.results-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.results-header h2 { font-size:16px; }

table { width:100%; border-collapse:collapse; font-size:13px; }
thead th { background:#1a2634; padding:10px 8px; text-align:left; border-bottom:1px solid #2a3a4a; cursor:pointer; white-space:nowrap; user-select:none; }
thead th:hover { color:#4fc3f7; }
thead th.sorted { color:#4fc3f7; }
tbody tr { border-bottom:1px solid #1a2634; cursor:pointer; transition:background .15s; }
tbody tr:hover { background:#1a2634; }
tbody td { padding:8px; white-space:nowrap; }
.positive { color:#66bb6a; }
.negative { color:#ef5350; }
.rating-badge { display:inline-block; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:700; }
.rating-AA { background:#4fc3f7; color:#0f1923; }
.rating-A { background:#66bb6a; color:#0f1923; }
.rating-B { background:#ffb74d; color:#0f1923; }
.rating-C { background:#ef5350; color:#fff; }
.rating-D { background:#777; color:#fff; }

.chart-row td { padding:16px; background:#111b24; }
.chart-row img { max-width:100%; border-radius:8px; }

.history-section { margin-top:24px; }
.history-section h3 { font-size:14px; margin-bottom:8px; color:#90a4ae; }
.history-item { padding:8px 12px; background:#1a2634; border-radius:6px; margin-bottom:6px; display:flex; justify-content:space-between; font-size:12px; cursor:pointer; }
.history-item:hover { background:#243442; }

.schedule-panel { background:#1a2634; border-radius:8px; padding:16px; margin-top:16px; display:none; }
.schedule-panel.show { display:block; }
.schedule-row { display:flex; gap:12px; align-items:center; margin-bottom:10px; font-size:13px; }

.preset-bar { display:flex; gap:8px; align-items:center; }
.preset-bar select { min-width:120px; }

.empty-state { text-align:center; padding:60px 20px; color:#607d8b; }
.empty-state p { margin-top:8px; font-size:14px; }

.custom-code-area { width:100%; min-height:120px; background:#111b24; border:1px solid #2a3a4a; color:#e0e0e0; font-family:'Fira Code',monospace; font-size:12px; padding:10px; border-radius:6px; resize:vertical; }

.mcap-fmt { font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
<div class="header">
  <div style="display:flex;align-items:center;gap:16px;">
    <a href="/" style="font-size:18px;">←</a>
    <h1>Stock Screener</h1>
    <span style="color:#607d8b;font-size:13px;">S&P 500 + Nasdaq 100</span>
  </div>
  <div class="actions">
    <div class="preset-bar">
      <select id="presetSelect"><option value="">-- Presets --</option></select>
      <button class="btn-secondary" onclick="savePreset()">Save</button>
    </div>
    <button class="btn-secondary" onclick="toggleSchedule()">⏰ Schedule</button>
    <button class="btn-primary" id="runBtn" onclick="runScreener()">▶ Run Screener</button>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <!-- Technical Filters -->
    <details class="filter-section" open>
      <summary>Technical Filters</summary>

      <div class="filter-item">
        <input type="checkbox" id="f_ma" data-filter="ma_arrangement">
        <label for="f_ma">MA Arrangement</label>
      </div>
      <div class="filter-params" id="p_ma">
        <select id="ma_direction"><option value="bullish">Bullish ↑</option><option value="bearish">Bearish ↓</option></select>
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_macd" data-filter="macd_golden_cross">
        <label for="f_macd">MACD Golden Cross</label>
      </div>
      <div class="filter-params" id="p_macd">
        <span>Lookback:</span><input type="number" id="macd_lookback" value="3" min="1" max="10">
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_kdj" data-filter="kdj_oversold_bounce">
        <label for="f_kdj">KDJ Oversold Bounce</label>
      </div>
      <div class="filter-params" id="p_kdj">
        <span>Lookback:</span><input type="number" id="kdj_lookback" value="3" min="1" max="10">
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_vol" data-filter="volume_breakout">
        <label for="f_vol">Volume Breakout</label>
      </div>
      <div class="filter-params" id="p_vol">
        <span>Multiplier:</span><input type="number" id="vol_multiplier" value="2.0" step="0.5" min="1">
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_rsi" data-filter="rsi_zone">
        <label for="f_rsi">RSI Zone</label>
      </div>
      <div class="filter-params" id="p_rsi">
        <input type="number" id="rsi_min" value="30" min="0" max="100" placeholder="min">
        <span>-</span>
        <input type="number" id="rsi_max" value="70" min="0" max="100" placeholder="max">
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_bb" data-filter="bb_squeeze">
        <label for="f_bb">Bollinger Band</label>
      </div>
      <div class="filter-params" id="p_bb">
        <select id="bb_mode"><option value="squeeze">Squeeze</option><option value="breakout">Breakout ↑</option></select>
        <span id="bb_width_wrap">Width &lt; <input type="number" id="bb_width" value="0.15" step="0.01" min="0.01" max="0.5" style="width:55px"></span>
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_atr" data-filter="atr_filter">
        <label for="f_atr">ATR Volatility</label>
      </div>
      <div class="filter-params" id="p_atr">
        <input type="number" id="atr_min" value="1" step="0.5" min="0" placeholder="min%">
        <span>-</span>
        <input type="number" id="atr_max" value="5" step="0.5" min="0" placeholder="max%">
      </div>
    </details>

    <!-- Fundamental Filters -->
    <details class="filter-section" open>
      <summary>Fundamental Filters</summary>

      <div class="filter-item">
        <input type="checkbox" id="f_pe" data-filter="pe_range">
        <label for="f_pe">PE Ratio</label>
      </div>
      <div class="filter-params" id="p_pe">
        <input type="number" id="pe_min" value="5" min="0" placeholder="min">
        <span>-</span>
        <input type="number" id="pe_max" value="30" min="0" placeholder="max">
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_cap" data-filter="market_cap">
        <label for="f_cap">Market Cap</label>
      </div>
      <div class="filter-params" id="p_cap">
        <select id="cap_tier"><option value="large">Large (>200B)</option><option value="mid">Mid (10-200B)</option><option value="small">Small (<10B)</option></select>
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_rev" data-filter="revenue_growth">
        <label for="f_rev">Revenue Growth</label>
      </div>
      <div class="filter-params" id="p_rev">
        <span>Min:</span><input type="number" id="rev_min" value="10" min="0" placeholder="%">%
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_roe" data-filter="roe_filter">
        <label for="f_roe">ROE</label>
      </div>
      <div class="filter-params" id="p_roe">
        <span>Min:</span><input type="number" id="roe_min" value="15" min="0" placeholder="%">%
      </div>

      <div class="filter-item">
        <input type="checkbox" id="f_div" data-filter="dividend_yield">
        <label for="f_div">Dividend Yield</label>
      </div>
      <div class="filter-params" id="p_div">
        <span>Min:</span><input type="number" id="div_min" value="1" step="0.5" min="0" placeholder="%">%
      </div>
    </details>

    <!-- Custom Code -->
    <details class="filter-section">
      <summary>Custom Code</summary>
      <textarea class="custom-code-area" id="customCode" placeholder="def filter(data, info):&#10;    # data: DataFrame with indicators&#10;    # info: dict with fundamentals&#10;    return data['RSI_14'].iloc[-1] < 40"></textarea>
    </details>
  </div>

  <div class="main">
    <!-- Progress -->
    <div class="progress-bar" id="progressBar">
      <div class="progress-fill" id="progressFill" style="width:0%"></div>
      <div class="progress-text" id="progressText">0%</div>
    </div>

    <!-- Schedule Panel -->
    <div class="schedule-panel" id="schedulePanel">
      <div class="schedule-row">
        <label><input type="checkbox" id="sch_enabled"> Enable scheduled scan</label>
      </div>
      <div class="schedule-row">
        <span>Frequency:</span>
        <select id="sch_freq"><option value="daily">Daily</option><option value="weekly">Weekly</option></select>
        <span>Days:</span>
        <select id="sch_days"><option value="mon-fri">Mon-Fri</option><option value="mon,wed,fri">Mon/Wed/Fri</option><option value="fri">Friday</option></select>
        <span>Time (ET):</span>
        <input type="number" id="sch_hour" value="16" min="0" max="23" style="width:50px">:<input type="number" id="sch_min" value="30" min="0" max="59" style="width:50px">
      </div>
      <div class="schedule-row">
        <span>Preset:</span>
        <select id="sch_preset"></select>
        <button class="btn-secondary" onclick="saveSchedule()">Save Schedule</button>
      </div>
    </div>

    <!-- Results -->
    <div class="results-header">
      <h2 id="resultsTitle">Results</h2>
      <span id="resultsCount" style="color:#607d8b;font-size:13px;"></span>
    </div>

    <div id="resultsArea">
      <div class="empty-state">
        <p>Configure filters and click <b>Run Screener</b> to scan stocks</p>
      </div>
    </div>

    <!-- History -->
    <div class="history-section">
      <h3>Run History</h3>
      <div id="historyList"></div>
    </div>
  </div>
</div>

<script>
let currentRunId = null;
let pollTimer = null;
let currentResults = [];

// ── Build filters config from UI ──
function buildFilters() {
  const filters = { technical: {}, fundamental: {} };

  // Technical
  if (el('f_ma').checked) filters.technical.ma_arrangement = { enabled: true, direction: el('ma_direction').value };
  if (el('f_macd').checked) filters.technical.macd_golden_cross = { enabled: true, lookback: int('macd_lookback') };
  if (el('f_kdj').checked) filters.technical.kdj_oversold_bounce = { enabled: true, lookback: int('kdj_lookback') };
  if (el('f_vol').checked) filters.technical.volume_breakout = { enabled: true, multiplier: float('vol_multiplier') };
  if (el('f_rsi').checked) filters.technical.rsi_zone = { enabled: true, min: int('rsi_min'), max: int('rsi_max') };
  if (el('f_bb').checked) filters.technical.bb_squeeze = { enabled: true, mode: el('bb_mode').value, width_threshold: parseFloat(el('bb_width').value) || 0.15 };
  if (el('f_atr').checked) filters.technical.atr_filter = { enabled: true, min_pct: float('atr_min'), max_pct: float('atr_max') };

  // Fundamental
  if (el('f_pe').checked) filters.fundamental.pe_range = { enabled: true, min: int('pe_min'), max: int('pe_max') };
  if (el('f_cap').checked) filters.fundamental.market_cap = { enabled: true, tier: el('cap_tier').value };
  if (el('f_rev').checked) filters.fundamental.revenue_growth = { enabled: true, min_pct: int('rev_min') };
  if (el('f_roe').checked) filters.fundamental.roe_filter = { enabled: true, min_pct: int('roe_min') };
  if (el('f_div').checked) filters.fundamental.dividend_yield = { enabled: true, min_pct: float('div_min') };

  return filters;
}

// ── Run screener ──
async function runScreener() {
  const filters = buildFilters();
  const customCode = el('customCode').value.trim();
  const presetId = el('presetSelect').value || null;

  el('runBtn').disabled = true;
  el('runBtn').textContent = '⏳ Running...';
  showProgress(0);

  try {
    const resp = await fetch('/api/screener/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ filters, custom_code: customCode, preset_id: presetId })
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert(err.detail || 'Failed to start');
      resetRunBtn();
      return;
    }
    const data = await resp.json();
    currentRunId = data.run_id;
    startPolling();
  } catch(e) {
    alert('Error: ' + e.message);
    resetRunBtn();
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!currentRunId) return;
    const resp = await fetch(`/api/screener/status/${currentRunId}`);
    const data = await resp.json();
    showProgress(data.progress_pct);

    if (data.status === 'completed') {
      clearInterval(pollTimer);
      pollTimer = null;
      showProgress(100);
      setTimeout(() => { hideProgress(); loadResults(currentRunId); resetRunBtn(); loadHistory(); }, 500);
    } else if (data.status === 'failed') {
      clearInterval(pollTimer);
      pollTimer = null;
      hideProgress();
      alert('Scan failed: ' + (data.error_message || 'Unknown error'));
      resetRunBtn();
    }
  }, 2000);
}

// ── Results display ──
async function loadResults(runId) {
  const resp = await fetch(`/api/screener/results/${runId}?sort_by=score&order=desc`);
  const data = await resp.json();
  currentResults = data.results;
  renderTable(currentResults);
  el('resultsCount').textContent = `${data.total_passed} stocks passed`;
}

function renderTable(results) {
  if (!results.length) {
    el('resultsArea').innerHTML = '<div class="empty-state"><p>No stocks passed the filters</p></div>';
    return;
  }

  let html = `<table><thead><tr>
    <th onclick="sortBy('symbol')">Symbol</th>
    <th onclick="sortBy('price')">Price</th>
    <th onclick="sortBy('change_pct')">Chg%</th>
    <th onclick="sortBy('score')">Score</th>
    <th onclick="sortBy('pe_ratio')">PE</th>
    <th onclick="sortBy('market_cap')">MCap</th>
    <th onclick="sortBy('revenue_growth')">Rev%</th>
    <th onclick="sortBy('roe')">ROE%</th>
  </tr></thead><tbody>`;

  for (const r of results) {
    const chgCls = (r.change_pct||0) >= 0 ? 'positive' : 'negative';
    const ratingCls = r.rating ? `rating-${r.rating}` : '';
    html += `<tr onclick="toggleChart(this,'${r.symbol}')">
      <td><b>${r.symbol}</b></td>
      <td>${r.price ? r.price.toFixed(2) : '-'}</td>
      <td class="${chgCls}">${r.change_pct != null ? (r.change_pct >= 0 ? '+' : '') + r.change_pct.toFixed(2) + '%' : '-'}</td>
      <td>${r.score ? r.score.toFixed(1) : '-'} <span class="rating-badge ${ratingCls}">${r.rating||''}</span></td>
      <td>${r.pe_ratio != null ? r.pe_ratio.toFixed(1) : '-'}</td>
      <td class="mcap-fmt">${fmtCap(r.market_cap)}</td>
      <td>${r.revenue_growth != null ? r.revenue_growth.toFixed(1)+'%' : '-'}</td>
      <td>${r.roe != null ? r.roe.toFixed(1)+'%' : '-'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  el('resultsArea').innerHTML = html;
}

let sortCol = 'score', sortDir = 'desc';
function sortBy(col) {
  if (sortCol === col) sortDir = sortDir === 'desc' ? 'asc' : 'desc';
  else { sortCol = col; sortDir = 'desc'; }
  currentResults.sort((a, b) => {
    let va = a[col], vb = b[col];
    if (col === 'symbol') { va = va||''; vb = vb||''; return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va); }
    va = va||0; vb = vb||0;
    return sortDir === 'asc' ? va - vb : vb - va;
  });
  renderTable(currentResults);
}

// ── Chart expansion ──
async function toggleChart(row, symbol) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains('chart-row')) {
    next.remove();
    return;
  }
  // Remove any existing chart rows
  document.querySelectorAll('.chart-row').forEach(r => r.remove());

  const chartRow = document.createElement('tr');
  chartRow.className = 'chart-row';
  chartRow.innerHTML = '<td colspan="8" style="text-align:center;padding:20px;">Loading chart...</td>';
  row.after(chartRow);

  try {
    const resp = await fetch(`/api/screener/chart/${symbol}`);
    const data = await resp.json();
    chartRow.innerHTML = `<td colspan="8"><img src="${data.chart_base64}" alt="${symbol} chart"></td>`;
  } catch(e) {
    chartRow.innerHTML = `<td colspan="8" style="color:#ef5350;">Failed to load chart</td>`;
  }
}

// ── History ──
async function loadHistory() {
  const resp = await fetch('/api/screener/runs');
  const runs = await resp.json();
  if (!runs.length) { el('historyList').innerHTML = '<p style="color:#607d8b;font-size:12px;">No runs yet</p>'; return; }
  el('historyList').innerHTML = runs.map(r => {
    const dt = r.started_at ? new Date(r.started_at).toLocaleString() : '';
    return `<div class="history-item" onclick="loadResults(${r.id})">
      <span>v${r.version} - ${dt} (${r.trigger})</span>
      <span>${r.passed_stocks}/${r.total_stocks} passed</span>
    </div>`;
  }).join('');
}

// ── Presets ──
async function loadPresets() {
  const resp = await fetch('/api/screener/presets');
  const presets = await resp.json();
  const sel = el('presetSelect');
  sel.innerHTML = '<option value="">-- Presets --</option>';
  const schSel = el('sch_preset');
  schSel.innerHTML = '<option value="">None</option>';
  for (const p of presets) {
    sel.innerHTML += `<option value="${p.id}">${p.name}</option>`;
    schSel.innerHTML += `<option value="${p.id}">${p.name}</option>`;
  }
  sel.onchange = () => { if(sel.value) applyPreset(presets.find(p=>p.id==+sel.value)); };
}

function applyPreset(preset) {
  if (!preset) return;
  try {
    const cfg = JSON.parse(preset.filters_json);
    // Reset all checkboxes
    document.querySelectorAll('[data-filter]').forEach(cb => cb.checked = false);

    // Apply technical
    const tech = cfg.technical || {};
    for (const [name, val] of Object.entries(tech)) {
      const cb = document.querySelector(`[data-filter="${name}"]`);
      if (cb && val.enabled) { cb.checked = true; applyFilterParams(name, val); }
    }
    // Apply fundamental
    const fund = cfg.fundamental || {};
    for (const [name, val] of Object.entries(fund)) {
      const cb = document.querySelector(`[data-filter="${name}"]`);
      if (cb && val.enabled) { cb.checked = true; applyFilterParams(name, val); }
    }
    if (preset.custom_code) el('customCode').value = preset.custom_code;
  } catch(e) { console.warn('Failed to apply preset', e); }
}

function applyFilterParams(name, val) {
  if (name==='ma_arrangement' && val.direction) el('ma_direction').value = val.direction;
  if (name==='macd_golden_cross' && val.lookback) el('macd_lookback').value = val.lookback;
  if (name==='kdj_oversold_bounce' && val.lookback) el('kdj_lookback').value = val.lookback;
  if (name==='volume_breakout' && val.multiplier) el('vol_multiplier').value = val.multiplier;
  if (name==='rsi_zone') { if(val.min!=null) el('rsi_min').value=val.min; if(val.max!=null) el('rsi_max').value=val.max; }
  if (name==='bb_squeeze' && val.mode) { el('bb_mode').value = val.mode; if (val.width_threshold) el('bb_width').value = val.width_threshold; }
  if (name==='atr_filter') { if(val.min_pct!=null) el('atr_min').value=val.min_pct; if(val.max_pct!=null) el('atr_max').value=val.max_pct; }
  if (name==='pe_range') { if(val.min!=null) el('pe_min').value=val.min; if(val.max!=null) el('pe_max').value=val.max; }
  if (name==='market_cap' && val.tier) el('cap_tier').value = val.tier;
  if (name==='revenue_growth' && val.min_pct!=null) el('rev_min').value = val.min_pct;
  if (name==='roe_filter' && val.min_pct!=null) el('roe_min').value = val.min_pct;
  if (name==='dividend_yield' && val.min_pct!=null) el('div_min').value = val.min_pct;
}

async function savePreset() {
  const name = prompt('Preset name:');
  if (!name) return;
  const filters = buildFilters();
  await fetch('/api/screener/presets', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, filters_json: JSON.stringify(filters), custom_code: el('customCode').value })
  });
  loadPresets();
}

// ── Schedule ──
function toggleSchedule() {
  el('schedulePanel').classList.toggle('show');
}

async function loadSchedule() {
  const resp = await fetch('/api/screener/schedule');
  const cfg = await resp.json();
  el('sch_enabled').checked = cfg.schedule_enabled;
  el('sch_freq').value = cfg.schedule_frequency;
  el('sch_days').value = cfg.schedule_day_of_week;
  el('sch_hour').value = cfg.schedule_hour;
  el('sch_min').value = cfg.schedule_minute;
  if (cfg.schedule_preset_id) el('sch_preset').value = cfg.schedule_preset_id;
}

async function saveSchedule() {
  await fetch('/api/screener/schedule', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      schedule_enabled: el('sch_enabled').checked,
      schedule_frequency: el('sch_freq').value,
      schedule_day_of_week: el('sch_days').value,
      schedule_hour: int('sch_hour'),
      schedule_minute: int('sch_min'),
      schedule_preset_id: el('sch_preset').value || null,
    })
  });
  alert('Schedule saved!');
}

// ── Utilities ──
function el(id) { return document.getElementById(id); }
function int(id) { return parseInt(el(id).value) || 0; }
function float(id) { return parseFloat(el(id).value) || 0; }

function showProgress(pct) {
  el('progressBar').classList.add('active');
  el('progressFill').style.width = pct + '%';
  el('progressText').textContent = pct + '%';
}
function hideProgress() { el('progressBar').classList.remove('active'); }
function resetRunBtn() { el('runBtn').disabled = false; el('runBtn').textContent = '▶ Run Screener'; }

function fmtCap(v) {
  if (!v) return '-';
  if (v >= 1e12) return (v/1e12).toFixed(1) + 'T';
  if (v >= 1e9) return (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v/1e6).toFixed(0) + 'M';
  return v.toFixed(0);
}

// ── Init ──
loadPresets();
loadSchedule();
loadHistory();
</script>
</body>
</html>"""
