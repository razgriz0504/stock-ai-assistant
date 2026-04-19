import os
import logging
import asyncio
from typing import Optional
from litellm import completion

from config import settings

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = {
    "gemini": "gemini/gemini-2.0-flash",
    "gemini3pro": "gemini/gemini-3.1-pro-preview",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "qwen": "dashscope/qwen-plus",
    "minimax": "openai/MiniMax-Text-01",
}

# Models that need custom API base URL
_CUSTOM_API_BASE = {
    "openai/MiniMax-Text-01": "https://api.minimax.chat/v1",
}

# Models that need a specific API key env var
_CUSTOM_API_KEY = {
    "openai/MiniMax-Text-01": "MINIMAX_API_KEY",
}

# Gemini safety settings: lower filtering to prevent SAFETY refusals on stock/finance topics
_GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

# Default timeout (seconds) for LLM calls
_LLM_TIMEOUT = 60

_current_model: str = settings.default_llm


def set_model(model_name: str) -> str:
    global _current_model
    if model_name in SUPPORTED_MODELS:
        _current_model = SUPPORTED_MODELS[model_name]
    else:
        _current_model = model_name
    return _current_model


def get_model() -> str:
    return _current_model


def list_models() -> dict:
    return SUPPORTED_MODELS.copy()


def _extract_grounding_sources(response) -> list[dict]:
    """从 Gemini 响应中提取 Google Search grounding 的引用来源"""
    sources = []
    # 优先从 _hidden_params 获取
    grounding_metadata = getattr(response, "_hidden_params", {}).get(
        "vertex_ai_grounding_metadata", []
    )
    if not grounding_metadata:
        grounding_metadata = getattr(response, "vertex_ai_grounding_metadata", [])

    for metadata in grounding_metadata:
        for chunk in metadata.get("groundingChunks", []):
            web = chunk.get("web", {})
            uri = web.get("uri", "")
            title = web.get("title", "")
            if uri:
                sources.append({"title": title, "url": uri})

    # 去重（按 url）
    seen = set()
    unique = []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)
    return unique


async def chat(
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    web_search: bool = False,
) -> str:
    use_model = model or _current_model
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        logger.info(f"Calling LLM: {use_model}")
        # 联网搜索模式需要更长的超时时间
        timeout = 120 if web_search else _LLM_TIMEOUT
        kwargs = {
            "model": use_model,
            "messages": messages,
            "timeout": timeout,
            "request_timeout": timeout,
        }

        if use_model in _CUSTOM_API_BASE:
            kwargs["api_base"] = _CUSTOM_API_BASE[use_model]
        if use_model in _CUSTOM_API_KEY:
            kwargs["api_key"] = os.environ.get(_CUSTOM_API_KEY[use_model], "")

        # Gemini: lower safety filtering to avoid SAFETY refusals
        if use_model.startswith("gemini/"):
            kwargs["safety_settings"] = _GEMINI_SAFETY_SETTINGS

        # Gemini: enable Google Search grounding when requested
        if web_search and use_model.startswith("gemini/"):
            kwargs["tools"] = [{"googleSearch": {}}]

        response = await asyncio.to_thread(completion, **kwargs)

        # Guard against empty response (e.g. SAFETY filter still blocks)
        if not response.choices:
            logger.warning(f"LLM returned empty choices ({use_model})")
            return "AI 返回为空，请稍后重试"

        content = response.choices[0].message.content
        if not content:
            logger.warning(f"LLM returned empty content ({use_model}), finish_reason={response.choices[0].finish_reason}")
            return "AI 返回内容为空，请稍后重试"

        # 若启用了联网搜索，追加引用来源
        if web_search:
            sources = _extract_grounding_sources(response)
            if sources:
                source_lines = []
                for i, s in enumerate(sources, 1):
                    source_lines.append(f"[{i}] [{s['title']}]({s['url']})")
                content += "\n\n---\n**数据来源**\n" + "\n".join(source_lines)

        return content
    except asyncio.TimeoutError:
        logger.error(f"LLM call timed out after {_LLM_TIMEOUT}s ({use_model})")
        return f"AI 调用超时，请稍后重试"
    except Exception as e:
        logger.error(f"LLM call failed ({use_model}): {e}")
        return f"AI 调用失败 ({use_model}): {e}"
