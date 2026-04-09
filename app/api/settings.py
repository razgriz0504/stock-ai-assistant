import os
import time
import logging
import asyncio
from pathlib import Path
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import settings
from app.llm.client import (
    SUPPORTED_MODELS, get_model, set_model,
    _CUSTOM_API_BASE, _CUSTOM_API_KEY,
)

logger = logging.getLogger(__name__)
router = APIRouter()

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# ── Provider metadata ──────────────────────────────────────────────
PROVIDER_CONFIG = OrderedDict([
    ("google", {
        "label": "Google Gemini",
        "key_field": "gemini_api_key",
        "env_var": "GEMINI_API_KEY",
        "models": ["gemini"],
        "test_model": "gemini",
    }),
    ("openai", {
        "label": "OpenAI",
        "key_field": "openai_api_key",
        "env_var": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "test_model": "gpt-4o-mini",
    }),
    ("dashscope", {
        "label": "Dashscope (通义千问)",
        "key_field": "dashscope_api_key",
        "env_var": "DASHSCOPE_API_KEY",
        "models": ["qwen"],
        "test_model": "qwen",
    }),
    ("minimax", {
        "label": "MiniMax",
        "key_field": "minimax_api_key",
        "env_var": "MINIMAX_API_KEY",
        "models": ["minimax"],
        "test_model": "minimax",
    }),
    ("finnhub", {
        "label": "Finnhub (行情数据)",
        "key_field": "finnhub_api_key",
        "env_var": "FINNHUB_API_KEY",
        "models": [],
        "test_model": None,
    }),
])

MODEL_DISPLAY = {
    "gemini": "Gemini 2.0 Flash",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini",
    "qwen": "通义千问 Qwen-Plus",
    "minimax": "MiniMax Text-01",
}

KNOWN_KEY_FIELDS = {p["key_field"] for p in PROVIDER_CONFIG.values()}


# ── .env file I/O ──────────────────────────────────────────────────
def read_env_file() -> OrderedDict:
    if not ENV_PATH.exists():
        return OrderedDict()
    result = OrderedDict()
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def write_env_file(data: OrderedDict):
    lines = ["# Auto-managed by Stock AI Assistant"]
    for k, v in data.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Request / Response models ─────────────────────────────────────
class SaveSettingsRequest(BaseModel):
    default_model: Optional[str] = None
    api_keys: Optional[dict] = None


class TestRequest(BaseModel):
    provider: str


# ── Helper: resolve current model short key ───────────────────────
def _current_model_key() -> str:
    current = get_model()
    inv = {v: k for k, v in SUPPORTED_MODELS.items()}
    return inv.get(current, current)


def _provider_for_model(model_key: str) -> Optional[str]:
    for pid, pc in PROVIDER_CONFIG.items():
        if model_key in pc["models"]:
            return pid
    return None


# ── GET /api/settings ──────────────────────────────────────────────
@router.get("/api/settings")
async def get_settings():
    models = {}
    for key, full_id in SUPPORTED_MODELS.items():
        provider = _provider_for_model(key)
        pc = PROVIDER_CONFIG.get(provider, {})
        key_field = pc.get("key_field", "")
        configured = bool(getattr(settings, key_field, "")) if key_field else False
        models[key] = {
            "display_name": MODEL_DISPLAY.get(key, key),
            "provider": provider,
            "available": configured,
        }

    api_keys = {}
    for pid, pc in PROVIDER_CONFIG.items():
        kf = pc["key_field"]
        api_keys[kf] = {
            "label": pc["label"],
            "provider": pid,
            "configured": bool(getattr(settings, kf, "")),
        }

    return {
        "current_model": _current_model_key(),
        "models": models,
        "api_keys": api_keys,
    }


# ── POST /api/settings ────────────────────────────────────────────
@router.post("/api/settings")
async def save_settings(req: SaveSettingsRequest):
    if req.default_model and req.default_model not in SUPPORTED_MODELS:
        raise HTTPException(400, f"不支持的模型: {req.default_model}")

    if req.api_keys:
        for field in req.api_keys:
            if field not in KNOWN_KEY_FIELDS:
                raise HTTPException(400, f"未知的配置项: {field}")

    # 1. Persist to .env
    env_data = read_env_file()

    if req.api_keys:
        for pid, pc in PROVIDER_CONFIG.items():
            kf = pc["key_field"]
            new_val = req.api_keys.get(kf, "")
            if new_val:
                env_data[pc["env_var"]] = new_val

    if req.default_model:
        env_data["DEFAULT_LLM"] = SUPPORTED_MODELS[req.default_model]

    # Ensure all known env vars exist in file
    for pid, pc in PROVIDER_CONFIG.items():
        if pc["env_var"] not in env_data:
            env_data[pc["env_var"]] = ""
    if "DEFAULT_LLM" not in env_data:
        env_data["DEFAULT_LLM"] = settings.default_llm
    if "CHARTS_DIR" not in env_data:
        env_data["CHARTS_DIR"] = "./charts"

    try:
        write_env_file(env_data)
    except PermissionError:
        raise HTTPException(500, "无法写入 .env 文件，请检查文件权限")

    # 2. Hot-reload runtime
    if req.api_keys:
        for pid, pc in PROVIDER_CONFIG.items():
            kf = pc["key_field"]
            new_val = req.api_keys.get(kf, "")
            if new_val:
                setattr(settings, kf, new_val)
    settings.setup_llm_env()

    if req.default_model:
        setattr(settings, "default_llm", SUPPORTED_MODELS[req.default_model])
        set_model(req.default_model)

    logger.info(f"Settings saved. Model: {get_model()}")
    return await get_settings()


# ── POST /api/settings/test ────────────────────────────────────────
@router.post("/api/settings/test")
async def test_connection(req: TestRequest):
    provider = req.provider
    pc = PROVIDER_CONFIG.get(provider)
    if not pc:
        raise HTTPException(400, f"未知的供应商: {provider}")

    key_field = pc["key_field"]
    configured = bool(getattr(settings, key_field, ""))
    if not configured:
        return {"success": False, "message": "请先填入 API Key 并保存", "response_time_ms": 0}

    # Finnhub: test with HTTP request
    if provider == "finnhub":
        return await _test_finnhub()

    test_model_key = pc.get("test_model")
    if not test_model_key or test_model_key not in SUPPORTED_MODELS:
        return {"success": False, "message": "该供应商没有可测试的模型", "response_time_ms": 0}

    full_model = SUPPORTED_MODELS[test_model_key]

    kwargs = {
        "model": full_model,
        "messages": [{"role": "user", "content": "Reply with OK"}],
        "timeout": 15,
    }
    if full_model in _CUSTOM_API_BASE:
        kwargs["api_base"] = _CUSTOM_API_BASE[full_model]
    if full_model in _CUSTOM_API_KEY:
        kwargs["api_key"] = os.environ.get(_CUSTOM_API_KEY[full_model], "")

    start = time.time()
    try:
        from litellm import completion
        response = await asyncio.to_thread(completion, **kwargs)
        elapsed = int((time.time() - start) * 1000)
        text = response.choices[0].message.content[:50]
        return {"success": True, "message": f"连接成功! ({elapsed}ms)", "response_time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        err = str(e)
        if "401" in err or "403" in err or "Unauthorized" in err:
            msg = "API Key 无效或已过期"
        elif "429" in err or "RESOURCE_EXHAUSTED" in err or "RateLimit" in err:
            return {"success": True, "message": f"Key 有效! (频率限制中，等1分钟即可正常使用) ({elapsed}ms)", "response_time_ms": elapsed}
        elif "timeout" in err.lower() or "timed out" in err.lower():
            msg = "连接超时，请检查网络"
        else:
            msg = f"连接失败: {err[:100]}"
        return {"success": False, "message": msg, "response_time_ms": elapsed}


async def _test_finnhub():
    import httpx
    key = getattr(settings, "finnhub_api_key", "")
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": "AAPL", "token": key},
            )
            elapsed = int((time.time() - start) * 1000)
            if resp.status_code == 200 and resp.json().get("c", 0) > 0:
                return {"success": True, "message": f"连接成功! ({elapsed}ms)", "response_time_ms": elapsed}
            elif resp.status_code == 401 or resp.status_code == 403:
                return {"success": False, "message": "API Key 无效", "response_time_ms": elapsed}
            else:
                return {"success": False, "message": f"返回异常: {resp.status_code}", "response_time_ms": elapsed}
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return {"success": False, "message": f"连接失败: {str(e)[:80]}", "response_time_ms": elapsed}


# ── Settings HTML Page ─────────────────────────────────────────────
SETTINGS_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Settings - Stock AI Assistant</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; }
.header { background: #1a2634; padding: 16px 24px; border-bottom: 1px solid #2a3a4a; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 18px; color: #4fc3f7; }
.header a { color: #4fc3f7; text-decoration: none; font-size: 14px; }
.header a:hover { text-decoration: underline; }
.content { flex: 1; padding: 24px; max-width: 800px; margin: 0 auto; width: 100%; }
.section { margin-bottom: 32px; }
.section-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #b0bec5; border-bottom: 1px solid #2a3a4a; padding-bottom: 8px; }
.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.model-card { background: #1a2634; border: 2px solid #2a3a4a; border-radius: 10px; padding: 16px; cursor: pointer; transition: all 0.2s; }
.model-card:hover { border-color: #37474f; background: #1e2d3d; }
.model-card.selected { border-color: #4fc3f7; background: #1a2f40; }
.model-card .name { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.model-card .provider { font-size: 12px; color: #78909c; margin-bottom: 8px; }
.model-card .badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; display: inline-block; }
.badge.ok { background: #1b3a1b; color: #66bb6a; }
.badge.warn { background: #3a2e1b; color: #ffa726; }
.key-row { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
.key-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.key-label { font-size: 14px; font-weight: 600; }
.key-status { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.key-status.on { background: #1b3a1b; color: #66bb6a; }
.key-status.off { background: #2d1a1a; color: #ef5350; }
.key-input-row { display: flex; gap: 8px; align-items: center; }
.key-input-row input { flex: 1; padding: 10px 14px; border-radius: 8px; border: 1px solid #2a3a4a; background: #0f1923; color: #e0e0e0; font-size: 13px; outline: none; font-family: monospace; }
.key-input-row input:focus { border-color: #4fc3f7; }
.btn-test { padding: 10px 16px; background: #263238; color: #4fc3f7; border: 1px solid #2a3a4a; border-radius: 8px; cursor: pointer; font-size: 13px; white-space: nowrap; }
.btn-test:hover { background: #2a3a4a; }
.btn-test:disabled { color: #546e7a; cursor: not-allowed; }
.btn-test.success { background: #1b3a1b; color: #66bb6a; border-color: #66bb6a; }
.btn-test.fail { background: #2d1a1a; color: #ef5350; border-color: #ef5350; }
.test-msg { font-size: 12px; margin-top: 6px; min-height: 18px; }
.test-msg.ok { color: #66bb6a; }
.test-msg.err { color: #ef5350; }
.footer { position: sticky; bottom: 0; background: #1a2634; border-top: 1px solid #2a3a4a; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
.btn-save { padding: 12px 32px; background: #1565c0; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 15px; font-weight: 600; }
.btn-save:hover { background: #1976d2; }
.btn-save:disabled { background: #37474f; cursor: not-allowed; }
.save-status { font-size: 14px; }
.save-status.ok { color: #66bb6a; }
.save-status.err { color: #ef5350; }
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #546e7a; border-top-color: #4fc3f7; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 600px) {
  .content { padding: 16px; }
  .model-grid { grid-template-columns: 1fr; }
  .key-input-row { flex-direction: column; }
  .btn-test { width: 100%; text-align: center; }
}
</style>
</head>
<body>
<div class="header">
  <h1>Settings</h1>
  <a href="/chat">← Back to Chat</a>
</div>
<div class="content">
  <div class="section">
    <div class="section-title">AI Model</div>
    <div class="model-grid" id="modelGrid"></div>
  </div>
  <div class="section">
    <div class="section-title">API Keys</div>
    <div id="keyList"></div>
  </div>
</div>
<div class="footer">
  <button class="btn-save" id="saveBtn" onclick="saveSettings()">Save</button>
  <span class="save-status" id="saveStatus"></span>
</div>

<script>
let selectedModel = '';
let settingsData = null;

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    settingsData = await res.json();
    selectedModel = settingsData.current_model;
    renderModels();
    renderKeys();
  } catch(e) {
    document.getElementById('saveStatus').textContent = 'Load failed: ' + e.message;
    document.getElementById('saveStatus').className = 'save-status err';
  }
}

function renderModels() {
  const grid = document.getElementById('modelGrid');
  grid.innerHTML = '';
  const providerLabels = {};
  for (const [kf, info] of Object.entries(settingsData.api_keys)) {
    providerLabels[info.provider] = info.label;
  }
  for (const [key, m] of Object.entries(settingsData.models)) {
    const card = document.createElement('div');
    card.className = 'model-card' + (key === selectedModel ? ' selected' : '');
    const badgeCls = m.available ? 'badge ok' : 'badge warn';
    const badgeTxt = m.available ? 'Available' : 'Need Key';
    card.innerHTML = '<div class="name">' + (key === selectedModel ? '● ' : '○ ') + m.display_name + '</div>'
      + '<div class="provider">' + (providerLabels[m.provider] || m.provider) + '</div>'
      + '<span class="' + badgeCls + '">' + badgeTxt + '</span>';
    card.onclick = () => { selectedModel = key; renderModels(); };
    grid.appendChild(card);
  }
}

function renderKeys() {
  const list = document.getElementById('keyList');
  list.innerHTML = '';
  for (const [field, info] of Object.entries(settingsData.api_keys)) {
    const row = document.createElement('div');
    row.className = 'key-row';
    const statusCls = info.configured ? 'key-status on' : 'key-status off';
    const statusTxt = info.configured ? 'Configured' : 'Not Set';
    const placeholder = info.configured ? 'Configured (leave empty to keep)' : 'Enter API Key...';
    const provider = info.provider;
    const showTest = provider !== 'finnhub' ? true : (info.configured ? true : false);
    const testBtn = showTest
      ? '<button class="btn-test" id="test_' + provider + '" onclick="testConn(\\'' + provider + '\\')">Test</button>'
      : '';
    row.innerHTML = '<div class="key-header"><span class="key-label">' + info.label + '</span><span class="' + statusCls + '">' + statusTxt + '</span></div>'
      + '<div class="key-input-row"><input type="password" id="key_' + field + '" placeholder="' + placeholder + '" autocomplete="off">' + testBtn + '</div>'
      + '<div class="test-msg" id="msg_' + provider + '"></div>';
    list.appendChild(row);
  }
}

async function testConn(provider) {
  const btn = document.getElementById('test_' + provider);
  const msg = document.getElementById('msg_' + provider);
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  btn.className = 'btn-test';
  msg.textContent = '';
  msg.className = 'test-msg';
  try {
    const res = await fetch('/api/settings/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({provider: provider})
    });
    const data = await res.json();
    if (data.success) {
      btn.textContent = 'OK';
      btn.className = 'btn-test success';
      msg.textContent = data.message;
      msg.className = 'test-msg ok';
    } else {
      btn.textContent = 'Fail';
      btn.className = 'btn-test fail';
      msg.textContent = data.message;
      msg.className = 'test-msg err';
    }
  } catch(e) {
    btn.textContent = 'Error';
    btn.className = 'btn-test fail';
    msg.textContent = e.message;
    msg.className = 'test-msg err';
  }
  setTimeout(() => { btn.textContent = 'Test'; btn.className = 'btn-test'; btn.disabled = false; }, 4000);
}

async function saveSettings() {
  const btn = document.getElementById('saveBtn');
  const status = document.getElementById('saveStatus');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Saving...';
  status.textContent = '';
  const keys = {};
  for (const [field] of Object.entries(settingsData.api_keys)) {
    const input = document.getElementById('key_' + field);
    if (input && input.value.trim()) keys[field] = input.value.trim();
  }
  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({default_model: selectedModel, api_keys: Object.keys(keys).length > 0 ? keys : null})
    });
    const data = await res.json();
    if (res.ok) {
      settingsData = data;
      renderModels();
      renderKeys();
      status.textContent = 'Saved!';
      status.className = 'save-status ok';
    } else {
      status.textContent = 'Error: ' + (data.detail || 'Unknown');
      status.className = 'save-status err';
    }
  } catch(e) {
    status.textContent = 'Network error: ' + e.message;
    status.className = 'save-status err';
  }
  btn.disabled = false;
  btn.innerHTML = 'Save';
  setTimeout(() => { status.textContent = ''; }, 5000);
}

loadSettings();
</script>
</body>
</html>"""


@router.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return SETTINGS_HTML
