import os
import time
import logging
import asyncio
from pathlib import Path
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, HTTPException
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
        from litellm import acompletion
        response = await asyncio.wait_for(acompletion(**kwargs), timeout=30)
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
