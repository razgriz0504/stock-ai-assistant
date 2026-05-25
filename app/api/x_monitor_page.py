"""X (Twitter) 关键账号舆情监控页面 + REST API"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.x_monitor.client import XAPIError, get_user_id_by_username, validate_bearer
from db.models import ReportConfig, SessionLocal, XAccount, XTweet, get_or_create_x_accounts

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────── Pydantic 请求模型 ───────────

class XAccountRequest(BaseModel):
    id: Optional[int] = None
    username: str
    display_name: Optional[str] = ""
    category: Optional[str] = ""
    enabled: Optional[bool] = True
    note: Optional[str] = ""


class XConfigRequest(BaseModel):
    x_api_bearer_token: Optional[str] = None
    x_monitor_enabled: Optional[bool] = None
    x_monitor_interval_hours: Optional[int] = None


# ─────────── 工具 ───────────

def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 12:
        return "*" * len(token)
    return token[:6] + "*" * 8 + token[-4:]


def _resolve_bearer(config: ReportConfig) -> str:
    import os
    return (os.getenv("X_API_BEARER_TOKEN", "").strip()
            or (config.x_api_bearer_token or "").strip())


def _account_to_dict(a: XAccount) -> dict:
    return {
        "id": a.id,
        "username": a.username,
        "display_name": a.display_name or "",
        "category": a.category or "",
        "enabled": bool(a.enabled),
        "x_user_id": a.x_user_id or "",
        "last_tweet_id": a.last_tweet_id or "",
        "last_fetched_at": a.last_fetched_at.isoformat() if a.last_fetched_at else None,
        "note": a.note or "",
    }


def _tweet_to_dict(t: XTweet) -> dict:
    try:
        key_points = json.loads(t.key_points) if t.key_points else []
    except json.JSONDecodeError:
        key_points = []
    try:
        impact_assets = json.loads(t.impact_assets) if t.impact_assets else []
    except json.JSONDecodeError:
        impact_assets = []
    try:
        metrics = json.loads(t.metrics) if t.metrics else {}
    except json.JSONDecodeError:
        metrics = {}
    return {
        "id": t.id,
        "tweet_id": t.tweet_id,
        "username": t.username,
        "text": t.text or "",
        "text_zh": t.text_zh or "",
        "key_points": key_points,
        "sentiment": t.sentiment or "",
        "impact_assets": impact_assets,
        "market_impact": t.market_impact or "",
        "metrics": metrics,
        "created_at_x": t.created_at_x.isoformat() if t.created_at_x else None,
        "fetched_at": t.fetched_at.isoformat() if t.fetched_at else None,
        "processed": bool(t.processed),
        "processing_error": t.processing_error or "",
    }


# ─────────── 账号 CRUD ───────────

@router.get("/api/x-monitor/accounts")
async def list_x_accounts():
    db = SessionLocal()
    try:
        # 确保有种子账号
        get_or_create_x_accounts(db)
        accounts = db.query(XAccount).order_by(XAccount.category, XAccount.username).all()
        return {"accounts": [_account_to_dict(a) for a in accounts]}
    finally:
        db.close()


@router.post("/api/x-monitor/accounts")
async def upsert_x_account(req: XAccountRequest):
    username = (req.username or "").strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=400, detail="username 不能为空")
    db = SessionLocal()
    try:
        if req.id:
            acc = db.query(XAccount).filter_by(id=req.id).first()
            if not acc:
                raise HTTPException(status_code=404, detail="账号不存在")
            acc.username = username
            acc.display_name = req.display_name or acc.display_name
            acc.category = req.category or acc.category
            acc.enabled = req.enabled if req.enabled is not None else acc.enabled
            acc.note = req.note if req.note is not None else acc.note
        else:
            existing = db.query(XAccount).filter_by(username=username).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"账号 @{username} 已存在")
            acc = XAccount(
                username=username,
                display_name=req.display_name or "",
                category=req.category or "",
                enabled=req.enabled if req.enabled is not None else True,
                note=req.note or "",
            )
            db.add(acc)

        # 尝试同步 x_user_id（失败不阻塞）
        config = db.query(ReportConfig).filter_by(id=1).first()
        bearer = _resolve_bearer(config) if config else ""
        if bearer and not acc.x_user_id:
            try:
                info = get_user_id_by_username(username, bearer)
                acc.x_user_id = info["id"]
                if not acc.display_name:
                    acc.display_name = info.get("name", "")
            except XAPIError as exc:
                logger.warning("查询 X 用户 ID 失败: %s", exc)

        db.commit()
        db.refresh(acc)
        return {"success": True, "account": _account_to_dict(acc)}
    finally:
        db.close()


@router.delete("/api/x-monitor/accounts/{account_id}")
async def delete_x_account(account_id: int):
    db = SessionLocal()
    try:
        acc = db.query(XAccount).filter_by(id=account_id).first()
        if not acc:
            raise HTTPException(status_code=404, detail="账号不存在")
        db.delete(acc)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.post("/api/x-monitor/accounts/{account_id}/test")
async def test_x_account(account_id: int):
    """用当前 Bearer Token 验证账号可访问"""
    db = SessionLocal()
    try:
        acc = db.query(XAccount).filter_by(id=account_id).first()
        if not acc:
            raise HTTPException(status_code=404, detail="账号不存在")
        config = db.query(ReportConfig).filter_by(id=1).first()
        bearer = _resolve_bearer(config) if config else ""
        if not bearer:
            return {"success": False, "message": "Bearer Token 未配置"}
        try:
            info = get_user_id_by_username(acc.username, bearer)
            acc.x_user_id = info["id"]
            if not acc.display_name:
                acc.display_name = info.get("name", "")
            db.commit()
            return {"success": True, "message": f"已找到 @{acc.username}", "info": info}
        except XAPIError as exc:
            return {"success": False, "message": str(exc)}
    finally:
        db.close()


# ─────────── 配置（Bearer Token + 调度）───────────

@router.get("/api/x-monitor/config")
async def get_x_config():
    db = SessionLocal()
    try:
        config = db.query(ReportConfig).filter_by(id=1).first()
        if config is None:
            return {
                "bearer_token_masked": "",
                "has_token": False,
                "x_monitor_enabled": False,
                "x_monitor_interval_hours": 4,
            }
        token = config.x_api_bearer_token or ""
        return {
            "bearer_token_masked": _mask_token(token),
            "has_token": bool(token),
            "x_monitor_enabled": bool(getattr(config, "x_monitor_enabled", False)),
            "x_monitor_interval_hours": int(getattr(config, "x_monitor_interval_hours", 4) or 4),
        }
    finally:
        db.close()


@router.post("/api/x-monitor/config")
async def update_x_config(req: XConfigRequest):
    """更新 Token / 启用 / 间隔，并同步调度器"""
    from app.monitor.scheduler import add_x_monitor_job, remove_x_monitor_job

    db = SessionLocal()
    try:
        config = db.query(ReportConfig).filter_by(id=1).first()
        if config is None:
            config = ReportConfig(id=1)
            db.add(config)

        if req.x_api_bearer_token is not None and req.x_api_bearer_token.strip():
            # 仅在非脱敏值时更新
            if "*" not in req.x_api_bearer_token:
                config.x_api_bearer_token = req.x_api_bearer_token.strip()
        if req.x_monitor_enabled is not None:
            config.x_monitor_enabled = bool(req.x_monitor_enabled)
        if req.x_monitor_interval_hours is not None:
            config.x_monitor_interval_hours = max(1, int(req.x_monitor_interval_hours))

        db.commit()
        db.refresh(config)

        # 同步调度
        if getattr(config, "x_monitor_enabled", False):
            add_x_monitor_job(interval_hours=int(getattr(config, "x_monitor_interval_hours", 4) or 4))
        else:
            remove_x_monitor_job()

        return {
            "success": True,
            "x_monitor_enabled": bool(config.x_monitor_enabled),
            "x_monitor_interval_hours": int(config.x_monitor_interval_hours or 4),
            "bearer_token_masked": _mask_token(config.x_api_bearer_token or ""),
        }
    finally:
        db.close()


@router.post("/api/x-monitor/validate-token")
async def validate_token():
    """验证当前已存的 Token 是否有效"""
    db = SessionLocal()
    try:
        config = db.query(ReportConfig).filter_by(id=1).first()
        bearer = _resolve_bearer(config) if config else ""
        if not bearer:
            return {"valid": False, "message": "Bearer Token 未配置"}
        ok, msg = validate_bearer(bearer)
        return {"valid": ok, "message": msg}
    finally:
        db.close()


# ─────────── 手动触发 ───────────

@router.post("/api/x-monitor/fetch-now")
async def fetch_now():
    """手动触发一轮抓取 + AI 处理"""
    from app.x_monitor.scheduler_job import run_x_monitor_job

    try:
        result = await run_x_monitor_job(force_process=True)
        return {"success": True, **result}
    except Exception as exc:
        logger.exception("Manual fetch-now failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────── 推文流 ───────────

@router.get("/api/x-monitor/tweets")
async def list_x_tweets(username: str = "", days: int = 7, limit: int = 50, only_processed: bool = False):
    days = max(1, min(int(days or 7), 90))
    limit = max(1, min(int(limit or 50), 500))
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = db.query(XTweet).filter(XTweet.created_at_x >= cutoff)
        if username:
            q = q.filter(XTweet.username == username.strip().lstrip("@"))
        if only_processed:
            q = q.filter(XTweet.processed == True)  # noqa: E712
        tweets = q.order_by(XTweet.created_at_x.desc()).limit(limit).all()
        return {"tweets": [_tweet_to_dict(t) for t in tweets], "count": len(tweets)}
    finally:
        db.close()


# ─────────── 页面 ───────────

@router.get("/x-monitor", response_class=HTMLResponse)
async def x_monitor_page():
    return _build_html()


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X 关键账号舆情监控</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; max-width: 1400px; margin: 0 auto; }
h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
h2 { color: #81d4fa; font-size: 18px; margin: 0 0 12px 0; }
.subtitle { color: #78909c; font-size: 13px; margin-bottom: 24px; }
.subtitle a { color: #4fc3f7; text-decoration: none; margin-right: 16px; }
.subtitle a:hover { text-decoration: underline; }

.card { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 8px; padding: 18px; margin-bottom: 18px; }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.row > * { flex: 0 0 auto; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { color: #78909c; font-size: 12px; }
.field input, .field select {
    background: #0f1923; border: 1px solid #2a3a4a; color: #e0e0e0;
    padding: 8px 12px; border-radius: 6px; font-size: 13px; min-width: 180px;
}
.field input:focus, .field select:focus { border-color: #4fc3f7; outline: none; }
.field input[readonly] { color: #78909c; }
.btn { background: #4fc3f7; color: #0f1923; border: none; padding: 8px 16px;
       border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn:hover { background: #81d4fa; }
.btn.secondary { background: #2a3a4a; color: #e0e0e0; }
.btn.secondary:hover { background: #3a4a5a; }
.btn.danger { background: #ef5350; color: #fff; }
.btn.danger:hover { background: #f48a87; }
.btn.small { padding: 5px 10px; font-size: 12px; }

.toggle { display: inline-flex; align-items: center; gap: 8px; }
.toggle input { transform: scale(1.4); accent-color: #4fc3f7; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
table th, table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #2a3a4a; }
table th { color: #78909c; font-weight: normal; font-size: 12px; }
table tr:hover { background: rgba(79,195,247,0.05); }
.cat { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.cat-fed { background: #4527a0; color: #fff; }
.cat-macro { background: #ad1457; color: #fff; }
.cat-analyst { background: #00838f; color: #fff; }
.cat-ceo { background: #ef6c00; color: #fff; }
.cat-media { background: #455a64; color: #fff; }
.cat-other { background: #37474f; color: #cfd8dc; }

.tweet { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 8px; padding: 14px; margin-bottom: 10px; }
.tweet-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.tweet-user { font-weight: 600; color: #4fc3f7; }
.tweet-meta { font-size: 11px; color: #78909c; }
.tweet-en { color: #b0bec5; font-size: 13px; line-height: 1.55; margin-bottom: 8px; padding: 8px; background: #0f1923; border-radius: 4px; }
.tweet-zh { color: #e0e0e0; font-size: 14px; line-height: 1.6; margin-bottom: 8px; }
.tweet-points { margin: 6px 0 8px 0; padding-left: 18px; }
.tweet-points li { color: #cfd8dc; font-size: 13px; line-height: 1.55; margin-bottom: 2px; }
.tweet-foot { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; font-size: 12px; }
.sent { padding: 2px 10px; border-radius: 10px; font-weight: 600; }
.sent.bullish { background: rgba(102,187,106,0.2); color: #66bb6a; }
.sent.bearish { background: rgba(239,83,80,0.2); color: #ef5350; }
.sent.neutral { background: rgba(120,144,156,0.2); color: #b0bec5; }
.asset-tag { background: #263238; color: #80deea; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; }
.market-impact { color: #ffca28; font-size: 12px; margin-top: 4px; font-style: italic; }

.toast { position: fixed; bottom: 20px; right: 20px; background: #263238; color: #fff;
         padding: 10px 18px; border-radius: 6px; font-size: 13px; z-index: 999;
         box-shadow: 0 4px 12px rgba(0,0,0,0.3); display: none; }
.toast.ok { background: #2e7d32; }
.toast.err { background: #c62828; }

.status { font-size: 12px; padding: 4px 8px; border-radius: 4px; }
.status.ok { background: rgba(102,187,106,0.2); color: #66bb6a; }
.status.warn { background: rgba(255,202,40,0.2); color: #ffca28; }
.empty { color: #546e7a; font-size: 13px; text-align: center; padding: 30px 0; }
.modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 100; }
.modal { display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%);
         background: #1a2634; padding: 24px; border-radius: 8px; min-width: 400px; z-index: 101; }
.modal.show, .modal-bg.show { display: block; }
.modal h3 { margin-bottom: 16px; color: #4fc3f7; }
.modal .field { margin-bottom: 12px; }
.modal .field input, .modal .field select { min-width: 100%; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
</style>
</head>
<body>
<h1>X 关键账号舆情监控</h1>
<p class="subtitle">
  捕捉关键账号在 X 上的言论 → AI 翻译/总结/影响评估 → 集成到周报
  <a href="/scoring">投研周报 →</a>
  <a href="/admin/report">报告管理 →</a>
</p>

<!-- 配置卡 -->
<div class="card">
  <h2>抓取配置</h2>
  <div class="row" style="margin-bottom: 12px;">
    <div class="field" style="flex: 1; min-width: 300px;">
      <label>X API Bearer Token</label>
      <input id="cfg-token" type="password" placeholder="输入 Bearer Token 后保存（或通过 X_API_BEARER_TOKEN 环境变量配置）">
    </div>
    <div class="field">
      <label>抓取间隔（小时）</label>
      <input id="cfg-interval" type="number" min="1" max="24" value="4">
    </div>
    <div class="field">
      <label>启用监控</label>
      <label class="toggle"><input id="cfg-enabled" type="checkbox"> 定时抓取</label>
    </div>
  </div>
  <div class="row">
    <button class="btn" onclick="saveConfig()">保存配置</button>
    <button class="btn secondary" onclick="validateToken()">验证 Token</button>
    <button class="btn secondary" onclick="fetchNow()">立即抓取</button>
    <span id="cfg-status" class="status"></span>
  </div>
</div>

<!-- 账号管理 -->
<div class="card">
  <div class="row" style="justify-content: space-between; margin-bottom: 12px;">
    <h2>监控账号（<span id="acc-count">0</span>）</h2>
    <button class="btn small" onclick="openAccountModal()">+ 添加账号</button>
  </div>
  <table>
    <thead>
      <tr>
        <th>Username</th>
        <th>名称</th>
        <th>分类</th>
        <th>启用</th>
        <th>X User ID</th>
        <th>最近抓取</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody id="acc-tbody"></tbody>
  </table>
</div>

<!-- 推文流 -->
<div class="card">
  <div class="row" style="justify-content: space-between; margin-bottom: 12px;">
    <h2>最新推文</h2>
    <div class="row">
      <select id="filter-username" onchange="loadTweets()">
        <option value="">全部账号</option>
      </select>
      <select id="filter-days" onchange="loadTweets()">
        <option value="1">最近 1 天</option>
        <option value="3">最近 3 天</option>
        <option value="7" selected>最近 7 天</option>
        <option value="30">最近 30 天</option>
      </select>
      <button class="btn small secondary" onclick="loadTweets()">刷新</button>
    </div>
  </div>
  <div id="tweets-area"><div class="empty">加载中...</div></div>
</div>

<!-- 添加/编辑账号弹窗 -->
<div id="modal-bg" class="modal-bg"></div>
<div id="modal" class="modal">
  <h3 id="modal-title">添加账号</h3>
  <div class="field">
    <label>Username（不带 @）</label>
    <input id="m-username" placeholder="例如: federalreserve">
  </div>
  <div class="field">
    <label>显示名称</label>
    <input id="m-display-name" placeholder="可选，留空将自动获取">
  </div>
  <div class="field">
    <label>分类</label>
    <select id="m-category">
      <option value="fed">fed - 央行/官方</option>
      <option value="macro">macro - 宏观经济</option>
      <option value="analyst">analyst - 分析师</option>
      <option value="ceo">ceo - 企业高管</option>
      <option value="media">media - 财经媒体</option>
      <option value="other">other - 其他</option>
    </select>
  </div>
  <div class="field">
    <label>备注</label>
    <input id="m-note" placeholder="可选">
  </div>
  <div class="field">
    <label class="toggle"><input id="m-enabled" type="checkbox" checked> 启用</label>
  </div>
  <div class="modal-actions">
    <button class="btn secondary" onclick="closeModal()">取消</button>
    <button class="btn" id="m-submit" onclick="submitAccount()">保存</button>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
let accounts = [];
let tweets = [];
let editingAccountId = null;

function toast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + (type || 'ok');
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

function fmtDate(s) {
  if (!s) return '—';
  try {
    const d = new Date(s);
    return d.toLocaleString('zh-CN', {hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
  } catch (e) { return s; }
}

async function loadConfig() {
  const r = await fetch('/api/x-monitor/config'); const d = await r.json();
  document.getElementById('cfg-token').placeholder = d.has_token ? '已配置: ' + d.bearer_token_masked + '（输入新值覆盖）' : '输入 Bearer Token';
  document.getElementById('cfg-interval').value = d.x_monitor_interval_hours;
  document.getElementById('cfg-enabled').checked = d.x_monitor_enabled;
}

async function saveConfig() {
  const body = {
    x_monitor_enabled: document.getElementById('cfg-enabled').checked,
    x_monitor_interval_hours: parseInt(document.getElementById('cfg-interval').value) || 4,
  };
  const tokenInput = document.getElementById('cfg-token').value.trim();
  if (tokenInput) body.x_api_bearer_token = tokenInput;
  const r = await fetch('/api/x-monitor/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const d = await r.json();
  if (d.success) {
    toast('配置已保存', 'ok');
    document.getElementById('cfg-token').value = '';
    loadConfig();
  } else {
    toast('保存失败', 'err');
  }
}

async function validateToken() {
  const el = document.getElementById('cfg-status');
  el.textContent = '验证中...'; el.className = 'status warn';
  try {
    const r = await fetch('/api/x-monitor/validate-token', {method:'POST'});
    const d = await r.json();
    el.textContent = d.message; el.className = 'status ' + (d.valid ? 'ok' : 'warn');
  } catch (e) {
    el.textContent = '验证失败: ' + e.message; el.className = 'status warn';
  }
}

async function fetchNow() {
  const el = document.getElementById('cfg-status');
  el.textContent = '抓取中（可能需要 1-2 分钟）...'; el.className = 'status warn';
  try {
    const r = await fetch('/api/x-monitor/fetch-now', {method:'POST'});
    const d = await r.json();
    if (d.success) {
      el.textContent = `账号 ${d.accounts_total}，新增 ${d.tweets_added}，AI 处理 ${d.processed}（失败 ${d.failed}）`;
      el.className = 'status ok';
      loadAccounts(); loadTweets();
    } else {
      el.textContent = '抓取失败';
      el.className = 'status warn';
    }
  } catch (e) {
    el.textContent = '抓取失败: ' + e.message; el.className = 'status warn';
  }
}

async function loadAccounts() {
  const r = await fetch('/api/x-monitor/accounts'); const d = await r.json();
  accounts = d.accounts || [];
  document.getElementById('acc-count').textContent = accounts.length;
  const tbody = document.getElementById('acc-tbody');
  tbody.innerHTML = accounts.map(a => `
    <tr>
      <td><strong>@${a.username}</strong></td>
      <td>${a.display_name || '—'}</td>
      <td><span class="cat cat-${a.category || 'other'}">${a.category || 'other'}</span></td>
      <td>${a.enabled ? '✓' : '—'}</td>
      <td><code style="font-size:11px;color:#78909c;">${a.x_user_id || '未解析'}</code></td>
      <td>${fmtDate(a.last_fetched_at)}</td>
      <td>
        <button class="btn small secondary" onclick="testAccount(${a.id})">测试</button>
        <button class="btn small secondary" onclick="editAccount(${a.id})">编辑</button>
        <button class="btn small danger" onclick="deleteAccount(${a.id})">删除</button>
      </td>
    </tr>
  `).join('');
  // 同步推文过滤选择
  const sel = document.getElementById('filter-username');
  const cur = sel.value;
  sel.innerHTML = '<option value="">全部账号</option>' + accounts.map(a => `<option value="${a.username}" ${cur===a.username?'selected':''}>@${a.username}</option>`).join('');
}

function openAccountModal(id) {
  editingAccountId = id || null;
  document.getElementById('modal-title').textContent = id ? '编辑账号' : '添加账号';
  document.getElementById('m-username').value = '';
  document.getElementById('m-display-name').value = '';
  document.getElementById('m-category').value = 'analyst';
  document.getElementById('m-note').value = '';
  document.getElementById('m-enabled').checked = true;
  if (id) {
    const a = accounts.find(x => x.id === id);
    if (a) {
      document.getElementById('m-username').value = a.username;
      document.getElementById('m-display-name').value = a.display_name || '';
      document.getElementById('m-category').value = a.category || 'analyst';
      document.getElementById('m-note').value = a.note || '';
      document.getElementById('m-enabled').checked = !!a.enabled;
    }
  }
  document.getElementById('modal').classList.add('show');
  document.getElementById('modal-bg').classList.add('show');
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
  document.getElementById('modal-bg').classList.remove('show');
  editingAccountId = null;
}

function editAccount(id) { openAccountModal(id); }

async function submitAccount() {
  const body = {
    id: editingAccountId,
    username: document.getElementById('m-username').value.trim(),
    display_name: document.getElementById('m-display-name').value.trim(),
    category: document.getElementById('m-category').value,
    note: document.getElementById('m-note').value.trim(),
    enabled: document.getElementById('m-enabled').checked,
  };
  if (!body.username) { toast('请输入 username', 'err'); return; }
  try {
    const r = await fetch('/api/x-monitor/accounts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const d = await r.json();
    if (r.ok && d.success) {
      toast('已保存', 'ok'); closeModal(); loadAccounts();
    } else {
      toast(d.detail || '保存失败', 'err');
    }
  } catch (e) {
    toast('请求失败: ' + e.message, 'err');
  }
}

async function deleteAccount(id) {
  const a = accounts.find(x => x.id === id);
  if (!confirm(`确认删除 @${a.username}？已抓取的历史推文不会被删除。`)) return;
  try {
    const r = await fetch('/api/x-monitor/accounts/' + id, {method:'DELETE'});
    if (r.ok) { toast('已删除', 'ok'); loadAccounts(); }
  } catch (e) { toast('删除失败', 'err'); }
}

async function testAccount(id) {
  try {
    const r = await fetch('/api/x-monitor/accounts/' + id + '/test', {method:'POST'});
    const d = await r.json();
    toast(d.message || (d.success ? '验证成功' : '验证失败'), d.success ? 'ok' : 'err');
    if (d.success) loadAccounts();
  } catch (e) { toast('测试失败: ' + e.message, 'err'); }
}

async function loadTweets() {
  const u = document.getElementById('filter-username').value;
  const days = document.getElementById('filter-days').value;
  const url = `/api/x-monitor/tweets?days=${days}&limit=100${u ? '&username='+u : ''}`;
  try {
    const r = await fetch(url); const d = await r.json();
    tweets = d.tweets || [];
    renderTweets();
  } catch (e) { document.getElementById('tweets-area').innerHTML = '<div class="empty">加载失败</div>'; }
}

function renderTweets() {
  const area = document.getElementById('tweets-area');
  if (!tweets.length) { area.innerHTML = '<div class="empty">暂无推文。点击「立即抓取」开始拉取。</div>'; return; }
  area.innerHTML = tweets.map(t => {
    const points = (t.key_points || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
    const assets = (t.impact_assets || []).map(a => `<span class="asset-tag">${escapeHtml(a)}</span>`).join(' ');
    const sent = t.sentiment || 'neutral';
    const metrics = t.metrics || {};
    const m = (metrics.like_count || metrics.retweet_count) ? `❤ ${metrics.like_count||0} · 🔁 ${metrics.retweet_count||0}` : '';
    return `<div class="tweet">
      <div class="tweet-head">
        <span class="tweet-user">@${t.username}</span>
        <span class="tweet-meta">${fmtDate(t.created_at_x)} · ${m}</span>
      </div>
      <div class="tweet-en">${escapeHtml(t.text)}</div>
      ${t.text_zh ? `<div class="tweet-zh">${escapeHtml(t.text_zh)}</div>` : ''}
      ${points ? `<ul class="tweet-points">${points}</ul>` : ''}
      <div class="tweet-foot">
        <span class="sent ${sent}">${sent}</span>
        ${assets}
        ${t.processed ? '' : '<span class="status warn">未处理</span>'}
      </div>
      ${t.market_impact ? `<div class="market-impact">📈 ${escapeHtml(t.market_impact)}</div>` : ''}
    </div>`;
  }).join('');
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
}

// 关闭弹窗：点背景
document.getElementById('modal-bg').addEventListener('click', closeModal);

// 初始化
loadConfig();
loadAccounts();
loadTweets();
</script>
</body>
</html>"""
