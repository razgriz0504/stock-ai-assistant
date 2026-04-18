"""投研周报管理页面 - 报告版本管理 + Prompt 配置 + 定时任务"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import SessionLocal, WeeklyReport, ReportConfig, UserPreference
from app.report.weekly_report import (
    generate_full_report,
    get_or_create_report_config,
    DEFAULT_MARKET_SYSTEM_PROMPT,
    DEFAULT_SECTOR_SYSTEM_PROMPT,
    DEFAULT_STOCKS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_USER_ID = "web_default"


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Pydantic Models ───

class GenerateRequest(BaseModel):
    watchlist: Optional[list[str]] = None


class PromptsUpdate(BaseModel):
    market_system_prompt: Optional[str] = None
    sector_system_prompt: Optional[str] = None
    stocks_system_prompt: Optional[str] = None


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[str] = None
    day_of_week: Optional[str] = None
    hour: Optional[int] = None
    minute: Optional[int] = None


# ─── API Endpoints ───

@router.get("/report-admin", response_class=HTMLResponse)
async def admin_page():
    return _build_html()


@router.get("/api/admin/reports")
async def list_reports(db: Session = Depends(_get_db)):
    """列出所有报告版本"""
    reports = db.query(WeeklyReport).order_by(WeeklyReport.version.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "status": r.status,
            "trigger": r.trigger,
            "model_name": r.model_name,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.post("/api/admin/reports/generate", status_code=202)
async def start_generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(_get_db),
):
    """异步生成周报（返回 202 Accepted，前端轮询状态）"""
    # 解析 watchlist
    watchlist = req.watchlist
    if watchlist is None:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        import json
        watchlist = json.loads(pref.watchlist) if pref and pref.watchlist else []

    # 先创建 DB 行拿到 report_id
    from app.report.weekly_report import _get_next_version, _resolve_prompts
    import json as _json

    config = get_or_create_report_config(db)
    market_prompt, sector_prompt, stocks_prompt = _resolve_prompts(config)
    from app.llm.client import get_model
    model_name = get_model()
    version = _get_next_version(db)

    report = WeeklyReport(
        version=version,
        report_date=datetime.now(timezone.utc),
        status="running",
        trigger="manual",
        model_name=model_name,
        market_system_prompt=market_prompt,
        sector_system_prompt=sector_prompt,
        stocks_system_prompt=stocks_prompt,
        watchlist_used=_json.dumps(watchlist),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    # 后台任务执行实际生成
    background_tasks.add_task(_run_generate, report_id, watchlist, market_prompt, sector_prompt)

    return {"report_id": report_id, "version": version, "status": "running"}


async def _run_generate(report_id: int, watchlist: list[str], market_prompt: str, sector_prompt: str):
    """后台任务：执行报告生成"""
    db = SessionLocal()
    try:
        report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
        if not report:
            return

        import asyncio
        import json
        from app.report.weekly_report import (
            fetch_index_data, fetch_sector_data,
            get_report_section_stocks,
            generate_ai_market_summary, generate_ai_sector_summary,
        )

        # 并行获取数据
        index_data, sector_data, stocks_data = await asyncio.gather(
            asyncio.to_thread(fetch_index_data),
            asyncio.to_thread(fetch_sector_data),
            get_report_section_stocks(watchlist),
        )

        # AI 分析
        ai_market_summary, ai_sector_summary = await asyncio.gather(
            generate_ai_market_summary(index_data, system_prompt=market_prompt),
            generate_ai_sector_summary(sector_data, system_prompt=sector_prompt),
        )

        # 序列化写入 DB
        report.index_data = json.dumps(index_data, ensure_ascii=False)
        report.sector_data = json.dumps(sector_data, ensure_ascii=False)
        report.watchlist_scores = json.dumps(stocks_data.get("watchlist_scores", []), ensure_ascii=False)
        report.hot_stock_scores = json.dumps(stocks_data.get("hot_stock_scores", []), ensure_ascii=False)
        report.ai_market_summary = ai_market_summary
        report.ai_sector_summary = ai_sector_summary
        report.status = "completed"
        db.commit()

        logger.info(f"Background report v{report.version} (id={report_id}) generated successfully")

    except Exception as e:
        logger.error(f"Background report generation failed (id={report_id}): {e}", exc_info=True)
        try:
            report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
            if report:
                report.status = "failed"
                report.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("/api/admin/reports/{report_id}/status")
async def get_report_status(report_id: int, db: Session = Depends(_get_db)):
    """轮询报告生成状态"""
    report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
    if not report:
        return {"error": "Report not found"}
    return {
        "id": report.id,
        "version": report.version,
        "status": report.status,
        "error_message": report.error_message,
    }


@router.get("/api/admin/prompts")
async def get_prompts(db: Session = Depends(_get_db)):
    """获取 Prompt 配置"""
    config = get_or_create_report_config(db)
    return {
        "market_system_prompt": config.default_market_system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT,
        "sector_system_prompt": config.default_sector_system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT,
        "stocks_system_prompt": config.default_stocks_system_prompt or DEFAULT_STOCKS_SYSTEM_PROMPT,
        "defaults": {
            "market_system_prompt": DEFAULT_MARKET_SYSTEM_PROMPT,
            "sector_system_prompt": DEFAULT_SECTOR_SYSTEM_PROMPT,
            "stocks_system_prompt": DEFAULT_STOCKS_SYSTEM_PROMPT,
        },
    }


@router.post("/api/admin/prompts")
async def update_prompts(req: PromptsUpdate, db: Session = Depends(_get_db)):
    """更新 Prompt 配置"""
    config = get_or_create_report_config(db)
    if req.market_system_prompt is not None:
        config.default_market_system_prompt = req.market_system_prompt
    if req.sector_system_prompt is not None:
        config.default_sector_system_prompt = req.sector_system_prompt
    if req.stocks_system_prompt is not None:
        config.default_stocks_system_prompt = req.stocks_system_prompt
    db.commit()
    db.refresh(config)
    return {"success": True}


@router.get("/api/admin/schedule")
async def get_schedule(db: Session = Depends(_get_db)):
    """获取定时任务配置"""
    config = get_or_create_report_config(db)
    return {
        "enabled": config.schedule_enabled,
        "frequency": config.schedule_frequency,
        "day_of_week": config.schedule_day_of_week,
        "hour": config.schedule_hour,
        "minute": config.schedule_minute,
    }


@router.post("/api/admin/schedule")
async def update_schedule(req: ScheduleUpdate, db: Session = Depends(_get_db)):
    """更新定时任务配置"""
    config = get_or_create_report_config(db)
    if req.enabled is not None:
        config.schedule_enabled = req.enabled
    if req.frequency is not None:
        config.schedule_frequency = req.frequency
    if req.day_of_week is not None:
        config.schedule_day_of_week = req.day_of_week
    if req.hour is not None:
        config.schedule_hour = req.hour
    if req.minute is not None:
        config.schedule_minute = req.minute
    db.commit()
    db.refresh(config)

    # 同步更新调度器
    _sync_scheduler(config)

    return {"success": True}


def _sync_scheduler(config: ReportConfig):
    """将 DB 配置同步到调度器"""
    from app.monitor.scheduler import (
        scheduler, add_report_job, remove_report_job,
    )
    try:
        if config.schedule_enabled:
            add_report_job(
                day_of_week=config.schedule_day_of_week,
                hour=config.schedule_hour,
                minute=config.schedule_minute,
            )
        else:
            remove_report_job()
    except Exception as e:
        logger.error(f"Failed to sync scheduler: {e}")


# ─── HTML ───

def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>周报管理</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #faf9f5; color: #1a1a1a; font-family: 'DM Sans', -apple-system, sans-serif; min-height: 100vh; }

.page-wrap { max-width: 1100px; margin: 0 auto; padding: 40px 32px; }
.head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid #e8e4de; }
.head-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; color: #c9774a; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.head-label::before { content: ''; display: inline-block; width: 6px; height: 6px; background: #c9774a; border-radius: 50%; }
.head h1 { font-family: 'Space Grotesk', sans-serif; font-size: 32px; font-weight: 700; margin: 0; }
.head h1 span { color: #c9774a; }
.head-right { display: flex; align-items: center; gap: 12px; }

/* Buttons */
.btn { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px 16px; border-radius: 6px; border: 1px solid #d4cfc7; background: #fff; color: #1a1a1a; cursor: pointer; transition: all .15s; }
.btn:hover { border-color: #c9774a; color: #c9774a; }
.btn-primary { background: #c9774a; color: #fff; border-color: #c9774a; }
.btn-primary:hover { background: #b5683e; border-color: #b5683e; color: #fff; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-sm { font-size: 11px; padding: 5px 10px; }
.btn-danger { color: #b91c1c; border-color: #b91c1c; }
.btn-danger:hover { background: #b91c1c; color: #fff; }

/* Tabs */
.tabs { display: flex; gap: 0; margin-bottom: 32px; border-bottom: 2px solid #e8e4de; }
.tab { font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: 1px; text-transform: uppercase; padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; color: #6b6560; transition: all .15s; }
.tab:hover { color: #1a1a1a; }
.tab.active { color: #c9774a; border-bottom-color: #c9774a; }

/* Tab content */
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Report Table */
.rpt-tbl { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e4de; border-radius: 10px; overflow: hidden; }
.rpt-tbl th { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: #6b6560; padding: 14px 16px; text-align: left; border-bottom: 1px solid #e8e4de; font-weight: 500; background: #faf9f5; }
.rpt-tbl td { padding: 12px 16px; border-bottom: 1px solid #f0ece6; font-size: 13px; }
.rpt-tbl tr:last-child td { border-bottom: none; }
.rpt-tbl tbody tr:hover { background: #faf9f5; }

/* Status badges */
.status { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.status.completed { background: rgba(45,106,79,0.08); color: #2d6a4f; }
.status.running { background: rgba(180,83,9,0.08); color: #b45309; }
.status.failed { background: rgba(185,28,28,0.08); color: #b91c1c; }

/* Form elements */
.form-group { margin-bottom: 24px; }
.form-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #6b6560; margin-bottom: 8px; display: block; }
.form-input, .form-textarea, .form-select { width: 100%; padding: 10px 14px; border: 1px solid #e8e4de; border-radius: 6px; font-family: 'DM Sans', sans-serif; font-size: 14px; background: #fff; color: #1a1a1a; transition: border-color .15s; }
.form-input:focus, .form-textarea:focus, .form-select:focus { outline: none; border-color: #c9774a; }
.form-textarea { min-height: 120px; resize: vertical; line-height: 1.6; }
.form-select { appearance: none; cursor: pointer; }
.form-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.form-hint { font-size: 11px; color: #a8a29e; margin-top: 4px; }

/* Card sections */
.card { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 24px; margin-bottom: 24px; }
.card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.card-title { font-family: 'Space Grotesk', sans-serif; font-size: 16px; font-weight: 600; }

/* Toggle */
.toggle-wrap { display: flex; align-items: center; gap: 12px; }
.toggle { position: relative; width: 44px; height: 24px; background: #d4cfc7; border-radius: 12px; cursor: pointer; transition: background .2s; }
.toggle.on { background: #c9774a; }
.toggle::after { content: ''; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; background: #fff; border-radius: 50%; transition: transform .2s; }
.toggle.on::after { transform: translateX(20px); }
.toggle-label { font-size: 13px; font-weight: 500; }

/* Links */
.head-subtitle { color: #6b6560; font-size: 13px; margin-bottom: 20px; }
.head-subtitle a { color: #c9774a; text-decoration: none; }
.head-subtitle a:hover { text-decoration: underline; }

/* Generation progress */
.gen-progress { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 24px; margin-bottom: 24px; display: none; }
.gen-progress.active { display: block; }
.gen-spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #e8e4de; border-top-color: #c9774a; border-radius: 50%; animation: spin .8s linear infinite; margin-right: 8px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Prompt preview */
.prompt-preview { background: #faf9f5; border: 1px solid #e8e4de; border-radius: 6px; padding: 12px; font-size: 12px; color: #6b6560; line-height: 1.6; margin-top: 8px; white-space: pre-wrap; max-height: 120px; overflow-y: auto; }

@media (max-width: 700px) {
  .form-row { grid-template-columns: 1fr; }
  .page-wrap { padding: 24px 16px; }
}
</style>
</head>
<body>
<div class="page-wrap">

  <div class="head">
    <div>
      <div class="head-label">Admin Console</div>
      <h1>周报<span>管理</span></h1>
    </div>
    <div class="head-right">
      <a href="/scoring" class="btn">&#x2190; 查看周报</a>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" data-tab="reports">报告版本</div>
    <div class="tab" data-tab="prompts">Prompt 配置</div>
    <div class="tab" data-tab="schedule">定时任务</div>
  </div>

  <!-- Tab: Reports -->
  <div class="tab-panel active" id="panel-reports">
    <div class="card">
      <div class="card-head">
        <span class="card-title">报告列表</span>
        <button class="btn btn-primary" id="btn-generate" onclick="startGenerate()">+ 生成新周报</button>
      </div>
      <div class="gen-progress" id="gen-progress">
        <span class="gen-spinner"></span>
        <span id="gen-status-text">正在生成报告...</span>
      </div>
      <table class="rpt-tbl">
        <thead>
          <tr>
            <th>版本</th><th>状态</th><th>触发方式</th><th>模型</th><th>生成时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody id="report-list">
          <tr><td colspan="6" style="text-align:center;color:#a8a29e;">加载中...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab: Prompts -->
  <div class="tab-panel" id="panel-prompts">
    <div class="card">
      <div class="card-head">
        <span class="card-title">Prompt 配置</span>
        <button class="btn btn-primary" onclick="savePrompts()">保存配置</button>
      </div>
      <div class="form-group">
        <label class="form-label">大盘综述 System Prompt</label>
        <textarea class="form-textarea" id="prompt-market"></textarea>
        <div class="form-hint">用于 AI 大盘综述生成的系统提示词，留空使用默认值</div>
      </div>
      <div class="form-group">
        <label class="form-label">行业分析 System Prompt</label>
        <textarea class="form-textarea" id="prompt-sector"></textarea>
        <div class="form-hint">用于 AI 行业轮动分析的系统提示词，留空使用默认值</div>
      </div>
      <div class="form-group">
        <label class="form-label">个股分析 System Prompt（预留）</label>
        <textarea class="form-textarea" id="prompt-stocks"></textarea>
        <div class="form-hint">预留字段，当前未使用</div>
      </div>
    </div>
  </div>

  <!-- Tab: Schedule -->
  <div class="tab-panel" id="panel-schedule">
    <div class="card">
      <div class="card-head">
        <span class="card-title">定时生成</span>
      </div>
      <div class="form-group">
        <div class="toggle-wrap">
          <div class="toggle" id="schedule-toggle" onclick="toggleSchedule()"></div>
          <span class="toggle-label" id="schedule-label">已关闭</span>
        </div>
      </div>
      <div id="schedule-config" style="opacity:0.4;pointer-events:none;">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">频率</label>
            <select class="form-select" id="sched-frequency">
              <option value="weekly">每周</option>
              <option value="daily">每天</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">星期</label>
            <select class="form-select" id="sched-day">
              <option value="mon">周一</option>
              <option value="tue">周二</option>
              <option value="wed">周三</option>
              <option value="thu">周四</option>
              <option value="fri" selected>周五</option>
              <option value="sat">周六</option>
              <option value="sun">周日</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">时间 (ET)</label>
            <div style="display:flex;gap:8px;">
              <input type="number" class="form-input" id="sched-hour" value="17" min="0" max="23" style="width:70px;">
              <span style="line-height:40px;">:</span>
              <input type="number" class="form-input" id="sched-minute" value="0" min="0" max="59" style="width:70px;">
            </div>
            <div class="form-hint">美东时间，夏令时 UTC-4 / 冬令时 UTC-5</div>
          </div>
        </div>
        <div style="margin-top:16px;">
          <button class="btn btn-primary" onclick="saveSchedule()">保存定时配置</button>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
/* ─── Tab switching ─── */
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
  });
});

/* ─── Reports list ─── */
let _pollTimer = null;

async function loadReports() {
  try {
    const resp = await fetch('/api/admin/reports');
    const reports = await resp.json();
    const tbody = document.getElementById('report-list');
    if (!reports.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#a8a29e;">暂无报告</td></tr>';
      return;
    }
    tbody.innerHTML = reports.map(r => {
      const date = r.report_date ? r.report_date.slice(0, 16).replace('T', ' ') : '-';
      return `<tr>
        <td><strong>v${r.version}</strong></td>
        <td><span class="status ${r.status}">${r.status}</span></td>
        <td>${r.trigger === 'scheduled' ? '定时' : '手动'}</td>
        <td style="font-family:'JetBrains Mono',monospace;font-size:11px;">${r.model_name || '-'}</td>
        <td style="font-family:'JetBrains Mono',monospace;font-size:11px;">${date}</td>
        <td>
          ${r.status === 'completed' ? `<a href="/scoring?v=${r.version}" class="btn btn-sm">查看</a>` : ''}
          ${r.status === 'failed' ? `<span style="color:#b91c1c;font-size:11px;" title="${r.error_message || ''}">失败</span>` : ''}
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    console.error('loadReports error:', e);
  }
}

async function startGenerate() {
  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = '生成中...';

  const progress = document.getElementById('gen-progress');
  const statusText = document.getElementById('gen-status-text');
  progress.classList.add('active');
  statusText.textContent = '正在生成报告...';

  try {
    const resp = await fetch('/api/admin/reports/generate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
    const data = await resp.json();

    if (resp.status === 202) {
      statusText.textContent = `报告 v${data.version} 生成中...`;
      // 开始轮询
      _pollTimer = setInterval(() => pollStatus(data.report_id, data.version), 3000);
    } else {
      statusText.textContent = '生成失败: ' + (data.detail || 'unknown error');
      btn.disabled = false;
      btn.textContent = '+ 生成新周报';
    }
  } catch (e) {
    statusText.textContent = '请求失败: ' + e.message;
    btn.disabled = false;
    btn.textContent = '+ 生成新周报';
  }
}

async function pollStatus(reportId, version) {
  try {
    const resp = await fetch(`/api/admin/reports/${reportId}/status`);
    const data = await resp.json();
    const statusText = document.getElementById('gen-status-text');

    if (data.status === 'completed') {
      clearInterval(_pollTimer);
      _pollTimer = null;
      statusText.textContent = `报告 v${version} 生成完成!`;
      const btn = document.getElementById('btn-generate');
      btn.disabled = false;
      btn.textContent = '+ 生成新周报';
      await loadReports();
      setTimeout(() => {
        document.getElementById('gen-progress').classList.remove('active');
      }, 3000);
    } else if (data.status === 'failed') {
      clearInterval(_pollTimer);
      _pollTimer = null;
      statusText.textContent = `报告 v${version} 生成失败: ${data.error_message || ''}`;
      const btn = document.getElementById('btn-generate');
      btn.disabled = false;
      btn.textContent = '+ 生成新周报';
      await loadReports();
    } else {
      statusText.textContent = `报告 v${version} 生成中... (${data.status})`;
    }
  } catch (e) {
    console.error('pollStatus error:', e);
  }
}

/* ─── Prompts ─── */
async function loadPrompts() {
  try {
    const resp = await fetch('/api/admin/prompts');
    const data = await resp.json();
    document.getElementById('prompt-market').value = data.market_system_prompt;
    document.getElementById('prompt-sector').value = data.sector_system_prompt;
    document.getElementById('prompt-stocks').value = data.stocks_system_prompt;
  } catch (e) {
    console.error('loadPrompts error:', e);
  }
}

async function savePrompts() {
  try {
    const resp = await fetch('/api/admin/prompts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        market_system_prompt: document.getElementById('prompt-market').value,
        sector_system_prompt: document.getElementById('prompt-sector').value,
        stocks_system_prompt: document.getElementById('prompt-stocks').value,
      }),
    });
    const data = await resp.json();
    if (data.success) {
      alert('Prompt 配置已保存');
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

/* ─── Schedule ─── */
let _scheduleEnabled = false;

async function loadSchedule() {
  try {
    const resp = await fetch('/api/admin/schedule');
    const data = await resp.json();
    _scheduleEnabled = data.enabled;
    updateScheduleUI();
    document.getElementById('sched-frequency').value = data.frequency;
    document.getElementById('sched-day').value = data.day_of_week;
    document.getElementById('sched-hour').value = data.hour;
    document.getElementById('sched-minute').value = data.minute;
  } catch (e) {
    console.error('loadSchedule error:', e);
  }
}

function updateScheduleUI() {
  const toggle = document.getElementById('schedule-toggle');
  const label = document.getElementById('schedule-label');
  const config = document.getElementById('schedule-config');
  if (_scheduleEnabled) {
    toggle.classList.add('on');
    label.textContent = '已开启';
    config.style.opacity = '1';
    config.style.pointerEvents = 'auto';
  } else {
    toggle.classList.remove('on');
    label.textContent = '已关闭';
    config.style.opacity = '0.4';
    config.style.pointerEvents = 'none';
  }
}

function toggleSchedule() {
  _scheduleEnabled = !_scheduleEnabled;
  updateScheduleUI();
}

async function saveSchedule() {
  try {
    const resp = await fetch('/api/admin/schedule', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        enabled: _scheduleEnabled,
        frequency: document.getElementById('sched-frequency').value,
        day_of_week: document.getElementById('sched-day').value,
        hour: parseInt(document.getElementById('sched-hour').value),
        minute: parseInt(document.getElementById('sched-minute').value),
      }),
    });
    const data = await resp.json();
    if (data.success) {
      alert('定时配置已保存');
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

/* ─── Init ─── */
(async function() {
  await Promise.all([loadReports(), loadPrompts(), loadSchedule()]);
})();
</script>
</body>
</html>"""
