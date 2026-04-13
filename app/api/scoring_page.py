"""选股打分页面 - 路由 + 内联 HTML（三 Tab：打分 / 历史版本 / 趋势看板）"""
import json
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from db.models import SessionLocal, UserPreference, ScoringRun, ScoringResult
from app.scoring.scorer import run_scoring

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_USER_ID = "web_default"

DEFAULT_SCORING_CODE = '''def score(data):
    """综合技术面打分策略"""
    import pandas as pd
    import numpy as np

    close = data['Close']
    total = 0
    details = {}

    # MACD 分析
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd_score = 3
    macd_text = "MACD 中性"
    if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]:
        macd_score = 5
        macd_text = "MACD 金叉形成，看涨信号"
    elif dif.iloc[-1] < dea.iloc[-1]:
        macd_score = 2
        macd_text = "MACD 处于空头排列"
    total += macd_score * 5
    details['MACD'] = {"score": macd_score, "analysis": macd_text}

    # RSI 分析
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_val = rsi.iloc[-1]
    rsi_score = 3
    rsi_text = f"RSI = {rsi_val:.0f}，中性区间"
    if rsi_val < 30:
        rsi_score = 5
        rsi_text = f"RSI = {rsi_val:.0f}，超卖区域，可能反弹"
    elif rsi_val > 70:
        rsi_score = 1
        rsi_text = f"RSI = {rsi_val:.0f}，超买区域，注意回调"
    total += rsi_score * 5
    details['RSI'] = {"score": rsi_score, "analysis": rsi_text}

    # 均线趋势
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    trend_score = 3
    trend_text = "均线交织，趋势不明"
    if close.iloc[-1] > ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]:
        trend_score = 5
        trend_text = "多头排列：价格 > MA5 > MA20 > MA60，强势上涨趋势"
    elif close.iloc[-1] < ma5.iloc[-1] < ma20.iloc[-1]:
        trend_score = 1
        trend_text = "空头排列，下跌趋势"
    total += trend_score * 5
    details['均线趋势'] = {"score": trend_score, "analysis": trend_text}

    # 成交量分析
    vol = data['Volume']
    vol_ma20 = vol.rolling(20).mean()
    vol_ratio = vol.iloc[-1] / vol_ma20.iloc[-1] if vol_ma20.iloc[-1] > 0 else 1
    vol_score = 3
    vol_text = f"量比 = {vol_ratio:.1f}，成交量正常"
    if vol_ratio > 2:
        vol_score = 5
        vol_text = f"量比 = {vol_ratio:.1f}，放量明显"
    elif vol_ratio < 0.5:
        vol_score = 2
        vol_text = f"量比 = {vol_ratio:.1f}，缩量"
    total += vol_score * 5
    details['成交量'] = {"score": vol_score, "analysis": vol_text}

    return {"score": total, "details": details}'''


class ScoringRequest(BaseModel):
    code: str
    period: str = "1y"


class ScheduleRequest(BaseModel):
    enabled: bool
    cron_hour: int = 16
    cron_minute: int = 30


# ─── API 路由 ───

@router.post("/api/scoring/run")
async def run_scoring_api(req: ScoringRequest):
    """手动触发打分"""
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        symbols = json.loads(pref.watchlist) if pref and pref.watchlist else []
    finally:
        db.close()

    result = run_scoring(req.code, symbols, req.period, trigger="manual")
    return result


@router.get("/api/scoring/history")
async def get_scoring_history():
    """获取历史版本列表"""
    db = SessionLocal()
    try:
        runs = db.query(ScoringRun).order_by(ScoringRun.id.desc()).limit(20).all()
        return {"runs": [{
            "id": r.id,
            "version": r.version,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "trigger": r.trigger,
            "stock_count": r.stock_count,
            "status": r.status,
        } for r in runs]}
    finally:
        db.close()


@router.get("/api/scoring/run/{run_id}")
async def get_scoring_run_detail(run_id: int):
    """获取某版本的详细结果"""
    db = SessionLocal()
    try:
        run = db.query(ScoringRun).filter(ScoringRun.id == run_id).first()
        if not run:
            return {"error": "版本不存在"}

        results = db.query(ScoringResult).filter(
            ScoringResult.run_id == run_id
        ).order_by(ScoringResult.score.desc().nullslast()).all()

        return {
            "run": {
                "id": run.id,
                "version": run.version,
                "created_at": run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "",
                "trigger": run.trigger,
                "stock_count": run.stock_count,
                "status": run.status,
            },
            "results": [{
                "symbol": r.symbol,
                "score": r.score,
                "rating": r.rating,
                "price": r.price,
                "change_pct": r.change_pct,
                "details": json.loads(r.details_json) if r.details_json else {},
                "error": r.error,
            } for r in results]
        }
    finally:
        db.close()


@router.get("/api/scoring/trend")
async def get_scoring_trend():
    """获取趋势看板数据"""
    db = SessionLocal()
    try:
        runs = db.query(ScoringRun).filter(
            ScoringRun.status == "completed"
        ).order_by(ScoringRun.id.asc()).limit(20).all()

        if not runs:
            return {"symbols": [], "versions": [], "matrix": {}}

        run_ids = [r.id for r in runs]
        versions = [f"v{r.version}" for r in runs]

        results = db.query(ScoringResult).filter(
            ScoringResult.run_id.in_(run_ids)
        ).all()

        # 构造 matrix: {symbol: {version_label: score}}
        symbol_set = set()
        matrix = {}
        run_id_to_version = {r.id: f"v{r.version}" for r in runs}

        for r in results:
            symbol_set.add(r.symbol)
            if r.symbol not in matrix:
                matrix[r.symbol] = {}
            ver = run_id_to_version.get(r.run_id, "")
            matrix[r.symbol][ver] = r.score

        symbols = sorted(symbol_set)
        return {"symbols": symbols, "versions": versions, "matrix": matrix}
    finally:
        db.close()


@router.post("/api/scoring/schedule")
async def set_scoring_schedule(req: ScheduleRequest):
    """设置/取消定时计划"""
    try:
        if req.enabled:
            from app.monitor.scheduler import add_scoring_job
            add_scoring_job(req.cron_hour, req.cron_minute)
            return {"success": True, "message": f"已设置定时打分：每个交易日 {req.cron_hour:02d}:{req.cron_minute:02d} ET"}
        else:
            from app.monitor.scheduler import remove_scoring_job
            remove_scoring_job()
            return {"success": True, "message": "已取消定时打分"}
    except Exception as e:
        return {"success": False, "message": f"设置失败: {str(e)}"}


@router.get("/api/scoring/schedule")
async def get_scoring_schedule():
    """获取当前定时计划状态"""
    from app.monitor.scheduler import scheduler
    job = scheduler.get_job("scoring_scheduled")
    if job:
        trigger = job.trigger
        return {"enabled": True, "cron_hour": trigger.fields[5].expressions[0].first, "cron_minute": trigger.fields[6].expressions[0].first}
    return {"enabled": False, "cron_hour": 16, "cron_minute": 30}


# ─── 页面 HTML ───

@router.get("/scoring", response_class=HTMLResponse)
async def scoring_page():
    return _build_html()


def _build_html() -> str:
    escaped_code = DEFAULT_SCORING_CODE.replace('`', '\\`').replace('${', '\\${')
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>选股打分</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }}
h1 {{ color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }}
.subtitle {{ color: #78909c; font-size: 13px; margin-bottom: 20px; }}
.subtitle a {{ color: #4fc3f7; text-decoration: none; }}
.subtitle a:hover {{ text-decoration: underline; }}

/* Tabs */
.tabs {{ display: flex; gap: 0; margin-bottom: 24px; border-bottom: 2px solid #1a2634; }}
.tab {{
    padding: 10px 24px; cursor: pointer; font-size: 14px; font-weight: 600;
    color: #78909c; border-bottom: 2px solid transparent; margin-bottom: -2px;
    transition: all .2s;
}}
.tab:hover {{ color: #b0bec5; }}
.tab.active {{ color: #4fc3f7; border-bottom-color: #4fc3f7; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* 通用控件 */
.params {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 16px; }}
.param-group {{ display: flex; flex-direction: column; gap: 4px; }}
.param-group label {{ font-size: 12px; color: #90a4ae; }}
.param-group select, .param-group input {{
    background: #1a2634; border: 1px solid #2a3a4a; color: #e0e0e0;
    padding: 8px 12px; border-radius: 6px; font-size: 14px;
}}
.param-group select:focus, .param-group input:focus {{ border-color: #4fc3f7; outline: none; }}

.code-area {{ margin-bottom: 16px; }}
.code-area label {{ font-size: 12px; color: #90a4ae; display: block; margin-bottom: 4px; }}
#code-editor {{
    width: 100%; min-height: 300px; background: #0d1117; border: 1px solid #2a3a4a;
    color: #c9d1d9; padding: 12px; border-radius: 6px; font-family: 'Consolas','Monaco',monospace;
    font-size: 13px; line-height: 1.5; resize: vertical; tab-size: 4;
}}
#code-editor:focus {{ border-color: #4fc3f7; outline: none; }}

.btn {{
    background: #4fc3f7; color: #0f1923; border: none; padding: 10px 28px;
    border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer;
}}
.btn:hover {{ background: #81d4fa; }}
.btn:disabled {{ background: #37474f; color: #607d8b; cursor: not-allowed; }}

.error-box {{
    background: #1a0000; border: 1px solid #d32f2f; border-radius: 6px; padding: 16px;
    font-family: monospace; font-size: 13px; color: #ef9a9a; white-space: pre-wrap;
    margin-top: 16px; display: none;
}}

/* 进度 */
.progress {{ color: #4fc3f7; font-size: 14px; margin-left: 16px; display: none; }}

/* 卡片 */
.cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }}
.card {{
    background: #1a2634; border: 1px solid #2a3a4a; border-radius: 10px;
    padding: 18px; position: relative;
}}
.card.error {{ border-color: #d32f2f; }}
.card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
.card-symbol {{ font-size: 18px; font-weight: 700; color: #e0e0e0; }}
.card-badge {{
    padding: 3px 12px; border-radius: 20px; font-size: 13px; font-weight: 700;
}}
.badge-AA {{ background: #1b5e20; color: #a5d6a7; }}
.badge-A {{ background: #2e7d32; color: #c8e6c9; }}
.badge-B {{ background: #e65100; color: #ffcc80; }}
.badge-C {{ background: #bf360c; color: #ffab91; }}
.badge-D {{ background: #b71c1c; color: #ef9a9a; }}
.card-score {{ font-size: 32px; font-weight: 800; color: #4fc3f7; margin-bottom: 8px; }}
.card-price {{ font-size: 13px; color: #90a4ae; margin-bottom: 12px; }}
.card-price .up {{ color: #66bb6a; }}
.card-price .down {{ color: #ef5350; }}
.card-details {{ border-top: 1px solid #2a3a4a; padding-top: 10px; }}
.detail-item {{ margin-bottom: 8px; }}
.detail-name {{ font-size: 12px; color: #78909c; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; }}
.detail-stars {{ color: #ffb74d; font-size: 11px; }}
.detail-text {{ font-size: 12px; color: #b0bec5; line-height: 1.4; }}

/* 定时设置 */
.schedule-box {{
    background: #1a2634; border: 1px solid #2a3a4a; border-radius: 8px;
    padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}}
.schedule-box label {{ font-size: 13px; color: #90a4ae; }}
.switch {{ position: relative; display: inline-block; width: 44px; height: 24px; }}
.switch input {{ opacity: 0; width: 0; height: 0; }}
.slider {{
    position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
    background: #37474f; border-radius: 24px; transition: .3s;
}}
.slider:before {{
    content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px;
    background: #e0e0e0; border-radius: 50%; transition: .3s;
}}
input:checked + .slider {{ background: #4fc3f7; }}
input:checked + .slider:before {{ transform: translateX(20px); }}
.schedule-time {{ display: flex; align-items: center; gap: 4px; }}
.schedule-time input {{
    width: 48px; background: #0d1117; border: 1px solid #2a3a4a; color: #e0e0e0;
    padding: 4px 6px; border-radius: 4px; font-size: 13px; text-align: center;
}}
.schedule-hint {{ font-size: 11px; color: #546e7a; }}

/* 历史版本表 */
.history-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.history-table th {{
    background: #1a2634; color: #90a4ae; padding: 10px 12px; text-align: left;
    border-bottom: 2px solid #2a3a4a; font-weight: 600;
}}
.history-table td {{ padding: 10px 12px; border-bottom: 1px solid #1a2634; }}
.history-table tr {{ cursor: pointer; transition: background .15s; }}
.history-table tr:hover {{ background: #1a2634; }}
.version-badge {{ background: #263238; padding: 2px 10px; border-radius: 12px; color: #4fc3f7; font-weight: 600; font-size: 12px; }}
.trigger-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; }}
.trigger-manual {{ background: #1a237e; color: #9fa8da; }}
.trigger-scheduled {{ background: #004d40; color: #80cbc4; }}

/* 版本详情展开 */
.run-detail {{ display: none; padding: 16px; background: #0f1923; }}
.run-detail.active {{ display: block; }}

/* 趋势看板 */
.trend-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.trend-table th {{
    background: #1a2634; color: #90a4ae; padding: 8px 12px; text-align: center;
    border: 1px solid #2a3a4a; font-weight: 600; position: sticky; top: 0;
}}
.trend-table td {{
    padding: 8px 12px; text-align: center; border: 1px solid #2a3a4a;
    font-weight: 600; font-size: 14px;
}}
.trend-table td.symbol-col {{ text-align: left; font-weight: 700; color: #e0e0e0; background: #1a2634; }}
.empty-state {{ color: #546e7a; text-align: center; padding: 40px 0; font-size: 14px; }}

@media (max-width: 900px) {{
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 600px) {{
    .cards {{ grid-template-columns: 1fr; }}
    .params {{ flex-direction: column; }}
}}
</style>
</head>
<body>
<h1>Stock Scoring</h1>
<p class="subtitle">选股打分系统 | <a href="/watchlist">管理关注列表</a></p>

<div class="tabs">
    <div class="tab active" onclick="switchTab(0)">打分</div>
    <div class="tab" onclick="switchTab(1)">历史版本</div>
    <div class="tab" onclick="switchTab(2)">趋势看板</div>
</div>

<!-- Tab 0: 打分 -->
<div class="tab-content active" id="tab-0">
    <div id="watchlist-info" style="color:#78909c;font-size:13px;margin-bottom:12px;"></div>

    <div class="schedule-box">
        <label>定时打分</label>
        <label class="switch">
            <input type="checkbox" id="schedule-toggle" onchange="toggleSchedule()">
            <span class="slider"></span>
        </label>
        <div class="schedule-time">
            <input type="number" id="cron-hour" value="16" min="0" max="23">
            <span style="color:#78909c">:</span>
            <input type="number" id="cron-minute" value="30" min="0" max="59">
            <span style="color:#546e7a;font-size:12px;margin-left:4px">ET</span>
        </div>
        <span class="schedule-hint">每个交易日按美东时间自动执行</span>
    </div>

    <div class="params">
        <div class="param-group">
            <label>数据范围</label>
            <select id="period">
                <option value="3mo">3 个月</option>
                <option value="6mo">6 个月</option>
                <option value="1y" selected>1 年</option>
            </select>
        </div>
    </div>

    <div class="code-area">
        <label>打分策略代码（Python）</label>
        <textarea id="code-editor">{escaped_code}</textarea>
    </div>

    <div style="display:flex;align-items:center;">
        <button class="btn" id="run-btn" onclick="runScoring()">运行打分</button>
        <span class="progress" id="progress"></span>
    </div>

    <div class="error-box" id="error-box"></div>
    <div class="cards" id="cards-container"></div>
</div>

<!-- Tab 1: 历史版本 -->
<div class="tab-content" id="tab-1">
    <div id="history-container"></div>
</div>

<!-- Tab 2: 趋势看板 -->
<div class="tab-content" id="tab-2">
    <div id="trend-container"></div>
</div>

<script>
// ─── Tab 切换 ───
function switchTab(idx) {{
    document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', i===idx));
    document.querySelectorAll('.tab-content').forEach((c,i) => c.classList.toggle('active', i===idx));
    if (idx === 1) loadHistory();
    if (idx === 2) loadTrend();
}}

// ─── Tab 键支持 ───
document.getElementById('code-editor').addEventListener('keydown', function(e) {{
    if (e.key === 'Tab') {{
        e.preventDefault();
        const s = this.selectionStart, end = this.selectionEnd;
        this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = s + 4;
    }}
}});

// ─── 加载关注列表信息 ───
async function loadWatchlistInfo() {{
    try {{
        const resp = await fetch('/api/watchlist');
        const data = await resp.json();
        const stocks = data.stocks || [];
        const el = document.getElementById('watchlist-info');
        if (stocks.length === 0) {{
            el.innerHTML = '当前关注列表为空，请先 <a href="/watchlist" style="color:#4fc3f7">添加股票</a>';
        }} else {{
            const preview = stocks.length > 5 ? stocks.slice(0,5).join(', ') + ` 等 ${{stocks.length}} 只` : stocks.join(', ');
            el.innerHTML = `当前关注: ${{preview}} (<a href="/watchlist" style="color:#4fc3f7">编辑</a>)`;
        }}
    }} catch(e) {{}}
}}

// ─── 加载定时设置 ───
async function loadSchedule() {{
    try {{
        const resp = await fetch('/api/scoring/schedule');
        const data = await resp.json();
        document.getElementById('schedule-toggle').checked = data.enabled;
        document.getElementById('cron-hour').value = data.cron_hour;
        document.getElementById('cron-minute').value = data.cron_minute;
    }} catch(e) {{}}
}}

async function toggleSchedule() {{
    const enabled = document.getElementById('schedule-toggle').checked;
    const hour = parseInt(document.getElementById('cron-hour').value) || 16;
    const minute = parseInt(document.getElementById('cron-minute').value) || 30;
    try {{
        await fetch('/api/scoring/schedule', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{enabled, cron_hour: hour, cron_minute: minute}})
        }});
    }} catch(e) {{}}
}}

// ─── 运行打分 ───
async function runScoring() {{
    const btn = document.getElementById('run-btn');
    const errBox = document.getElementById('error-box');
    const progress = document.getElementById('progress');
    const container = document.getElementById('cards-container');

    btn.disabled = true;
    btn.textContent = '执行中...';
    errBox.style.display = 'none';
    container.innerHTML = '';
    progress.style.display = 'inline';
    progress.textContent = '正在初始化...';

    const body = {{
        code: document.getElementById('code-editor').value,
        period: document.getElementById('period').value,
    }};

    try {{
        const resp = await fetch('/api/scoring/run', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
        }});
        const data = await resp.json();

        if (!data.success) {{
            errBox.textContent = data.error;
            errBox.style.display = 'block';
            return;
        }}

        renderCards(data.results);
    }} catch(e) {{
        errBox.textContent = '请求失败: ' + e.message;
        errBox.style.display = 'block';
    }} finally {{
        btn.disabled = false;
        btn.textContent = '运行打分';
        progress.style.display = 'none';
    }}
}}

// ─── 渲染卡片 ───
function renderCards(results) {{
    const container = document.getElementById('cards-container');
    if (!results || !results.length) {{
        container.innerHTML = '<div class="empty-state">无打分结果</div>';
        return;
    }}

    container.innerHTML = results.map(r => {{
        if (r.error) {{
            return `<div class="card error">
                <div class="card-header"><span class="card-symbol">${{r.symbol}}</span></div>
                <div style="color:#ef9a9a;font-size:13px">${{r.error}}</div>
            </div>`;
        }}

        const badge = r.rating || '-';
        const badgeCls = 'badge-' + badge;
        const priceLine = r.price ? `$${{r.price.toFixed(2)}}` : '-';
        const changeLine = r.change_pct != null
            ? `<span class="${{r.change_pct >= 0 ? 'up' : 'down'}}">${{r.change_pct >= 0 ? '+' : ''}}${{r.change_pct.toFixed(2)}}%</span>`
            : '';

        let detailsHtml = '';
        if (r.details && Object.keys(r.details).length > 0) {{
            detailsHtml = '<div class="card-details">' + Object.entries(r.details).map(([name, d]) => {{
                const stars = d.score != null ? '★'.repeat(Math.min(d.score, 5)) + '☆'.repeat(Math.max(5 - d.score, 0)) : '';
                return `<div class="detail-item">
                    <div class="detail-name">${{name}} <span class="detail-stars">${{stars}}</span></div>
                    <div class="detail-text">${{d.analysis || ''}}</div>
                </div>`;
            }}).join('') + '</div>';
        }}

        return `<div class="card">
            <div class="card-header">
                <span class="card-symbol">${{r.symbol}}</span>
                <span class="card-badge ${{badgeCls}}">${{badge}}</span>
            </div>
            <div class="card-score">${{r.score != null ? r.score : '-'}}</div>
            <div class="card-price">${{priceLine}} ${{changeLine}}</div>
            ${{detailsHtml}}
        </div>`;
    }}).join('');
}}

// ─── 历史版本 ───
async function loadHistory() {{
    const container = document.getElementById('history-container');
    container.innerHTML = '<div class="empty-state">加载中...</div>';

    try {{
        const resp = await fetch('/api/scoring/history');
        const data = await resp.json();
        const runs = data.runs || [];

        if (!runs.length) {{
            container.innerHTML = '<div class="empty-state">暂无历史版本，先运行一次打分</div>';
            return;
        }}

        let html = `<table class="history-table"><thead><tr>
            <th>版本</th><th>运行时间</th><th>触发方式</th><th>股票数</th><th>状态</th>
        </tr></thead><tbody>`;

        for (const r of runs) {{
            const triggerCls = r.trigger === 'scheduled' ? 'trigger-scheduled' : 'trigger-manual';
            const triggerText = r.trigger === 'scheduled' ? '定时' : '手动';
            const statusColor = r.status === 'completed' ? '#66bb6a' : r.status === 'failed' ? '#ef5350' : '#ffb74d';

            html += `<tr onclick="toggleRunDetail(${{r.id}}, this)">
                <td><span class="version-badge">v${{r.version}}</span></td>
                <td>${{r.created_at}}</td>
                <td><span class="trigger-badge ${{triggerCls}}">${{triggerText}}</span></td>
                <td>${{r.stock_count}}</td>
                <td style="color:${{statusColor}}">${{r.status}}</td>
            </tr>
            <tr><td colspan="5"><div class="run-detail" id="detail-${{r.id}}"></div></td></tr>`;
        }}

        html += '</tbody></table>';
        container.innerHTML = html;
    }} catch(e) {{
        container.innerHTML = `<div class="empty-state">加载失败: ${{e.message}}</div>`;
    }}
}}

async function toggleRunDetail(runId, row) {{
    const detail = document.getElementById('detail-' + runId);
    if (detail.classList.contains('active')) {{
        detail.classList.remove('active');
        return;
    }}

    // 关闭其他
    document.querySelectorAll('.run-detail.active').forEach(d => d.classList.remove('active'));

    detail.innerHTML = '<div style="color:#78909c;padding:10px">加载中...</div>';
    detail.classList.add('active');

    try {{
        const resp = await fetch(`/api/scoring/run/${{runId}}`);
        const data = await resp.json();

        if (data.results && data.results.length > 0) {{
            let html = '<div class="cards" style="margin-top:0">';
            for (const r of data.results) {{
                if (r.error) {{
                    html += `<div class="card error"><div class="card-header"><span class="card-symbol">${{r.symbol}}</span></div><div style="color:#ef9a9a;font-size:13px">${{r.error}}</div></div>`;
                }} else {{
                    const badge = r.rating || '-';
                    const badgeCls = 'badge-' + badge;
                    html += `<div class="card"><div class="card-header"><span class="card-symbol">${{r.symbol}}</span><span class="card-badge ${{badgeCls}}">${{badge}}</span></div><div class="card-score">${{r.score != null ? r.score : '-'}}</div></div>`;
                }}
            }}
            html += '</div>';
            detail.innerHTML = html;
        }} else {{
            detail.innerHTML = '<div style="color:#546e7a;padding:10px">无详细数据</div>';
        }}
    }} catch(e) {{
        detail.innerHTML = `<div style="color:#ef5350;padding:10px">加载失败: ${{e.message}}</div>`;
    }}
}}

// ─── 趋势看板 ───
async function loadTrend() {{
    const container = document.getElementById('trend-container');
    container.innerHTML = '<div class="empty-state">加载中...</div>';

    try {{
        const resp = await fetch('/api/scoring/trend');
        const data = await resp.json();

        if (!data.symbols || !data.symbols.length) {{
            container.innerHTML = '<div class="empty-state">暂无趋势数据，需要至少运行一次打分</div>';
            return;
        }}

        let html = '<div style="overflow-x:auto"><table class="trend-table"><thead><tr><th>股票</th>';
        for (const v of data.versions) {{
            html += `<th>${{v}}</th>`;
        }}
        html += '</tr></thead><tbody>';

        for (const sym of data.symbols) {{
            html += `<tr><td class="symbol-col">${{sym}}</td>`;
            for (const v of data.versions) {{
                const score = data.matrix[sym] && data.matrix[sym][v];
                if (score != null) {{
                    const bg = scoreColor(score);
                    html += `<td style="background:${{bg}};color:#fff">${{score}}</td>`;
                }} else {{
                    html += '<td style="color:#37474f">-</td>';
                }}
            }}
            html += '</tr>';
        }}

        html += '</tbody></table></div>';
        container.innerHTML = html;
    }} catch(e) {{
        container.innerHTML = `<div class="empty-state">加载失败: ${{e.message}}</div>`;
    }}
}}

function scoreColor(score) {{
    if (score >= 90) return 'rgba(27,94,32,0.7)';
    if (score >= 80) return 'rgba(46,125,50,0.6)';
    if (score >= 70) return 'rgba(230,81,0,0.5)';
    if (score >= 60) return 'rgba(191,54,12,0.5)';
    return 'rgba(183,28,28,0.5)';
}}

// ─── 初始化 ───
loadWatchlistInfo();
loadSchedule();
</script>
</body>
</html>"""
