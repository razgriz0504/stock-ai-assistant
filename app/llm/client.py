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


def _get_grounding_metadata(response) -> list[dict]:
    """增强型元数据提取：适配 Gemini 2.0/3.1 在 LiteLLM 中的返回结构"""

    # 路径 A: 检查 choices[0].message 的对象属性 (LiteLLM 最新版)
    try:
        msg = response.choices[0].message
        for attr in ["grounding_metadata", "groundingMetadata"]:
            if hasattr(msg, attr) and getattr(msg, attr):
                gm = getattr(msg, attr)
                return [gm] if isinstance(gm, dict) else gm
    except (AttributeError, IndexError):
        pass

    # 路径 B: 检查 additional_kwargs (OpenAI 兼容模式常用)
    try:
        ak = response.choices[0].message.additional_kwargs
        gm = ak.get("grounding_metadata") or ak.get("groundingMetadata")
        if gm:
            return [gm] if isinstance(gm, dict) else gm
    except (AttributeError, IndexError):
        pass

    # 路径 C: 检查 model_extra
    try:
        me = getattr(response, "model_extra", {}) or {}
        gm = me.get("grounding_metadata") or me.get("groundingMetadata")
        if gm:
            return [gm] if isinstance(gm, dict) else gm
    except (AttributeError, IndexError):
        pass

    # 路径 D: 降级到 _hidden_params (litellm 常规存储)
    hidden = getattr(response, "_hidden_params", {}) or {}
    for k in ["vertex_ai_grounding_metadata", "grounding_metadata"]:
        if hidden.get(k):
            return hidden[k]

    # 路径 E: 顶层属性
    for attr in ["vertex_ai_grounding_metadata", "grounding_metadata"]:
        gm = getattr(response, attr, None)
        if gm:
            return gm

    return []


def _add_inline_citations(text: str, grounding_metadata: list[dict]) -> str:
    """
    参照 Gemini 官方文档实现内联引用：
    使用 groundingSupports 将原文段落与 groundingChunks 中的来源关联，
    在对应位置插入 [1](url) 格式的引用链接。
    """
    if not grounding_metadata:
        return text

    # 合并所有 metadata 中的 chunks 和 supports
    all_chunks = []
    all_supports = []

    for metadata in grounding_metadata:
        chunks = metadata.get("groundingChunks", [])
        supports = metadata.get("groundingSupports", [])
        for chunk in chunks:
            all_chunks.append(chunk)
        for support in supports:
            all_supports.append(support)

    if not all_chunks or not all_supports:
        # 无 supports 时，降级为末尾追加来源列表
        return _append_source_list(text, all_chunks)

    # 按 endIndex 降序排列，避免插入时索引偏移
    sorted_supports = sorted(
        all_supports,
        key=lambda s: s.get("segment", {}).get("endIndex", 0),
        reverse=True,
    )

    for support in sorted_supports:
        segment = support.get("segment", {})
        end_index = segment.get("endIndex")
        chunk_indices = support.get("groundingChunkIndices", [])

        if end_index is None or not chunk_indices:
            continue
        if end_index > len(text):
            continue

        # 构建引用字符串：[1](url1), [2](url2)
        citation_links = []
        for i in chunk_indices:
            if i < len(all_chunks):
                web = all_chunks[i].get("web", {})
                uri = web.get("uri", "")
                if uri:
                    citation_links.append(f"[{i + 1}]({uri})")

        if citation_links:
            citation_string = " " + ", ".join(citation_links)
            text = text[:end_index] + citation_string + text[end_index:]

    # 末尾追加来源汇总
    return _append_source_list(text, all_chunks)


def _append_source_list(text: str, chunks: list[dict]) -> str:
    """在文本末尾追加去重后的来源列表"""
    seen_urls = set()
    source_lines = []
    for i, chunk in enumerate(chunks):
        web = chunk.get("web", {})
        uri = web.get("uri", "")
        title = web.get("title", "")
        if uri and uri not in seen_urls:
            seen_urls.add(uri)
            source_lines.append(f"[{i + 1}] [{title}]({uri})")

    if source_lines:
        text += "\n\n---\n**数据来源**\n" + "\n".join(source_lines)

    return text


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
        logger.info(f"Calling LLM: {use_model} (web_search={web_search})")
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
            kwargs["tools"] = [{"google_search": {}}]

        response = await asyncio.to_thread(completion, **kwargs)

        # Guard against empty response (e.g. SAFETY filter still blocks)
        if not response.choices:
            logger.warning(f"LLM returned empty choices ({use_model})")
            return "AI 返回为空，请稍后重试"

        content = response.choices[0].message.content
        if not content:
            logger.warning(f"LLM returned empty content ({use_model}), finish_reason={response.choices[0].finish_reason}")
            return "AI 返回内容为空，请稍后重试"

        # 若启用了联网搜索，提取 groundingMetadata 并添加内联引用
        if web_search:
            grounding_metadata = _get_grounding_metadata(response)
            if grounding_metadata:
                logger.info(f"Grounding metadata found: {len(grounding_metadata)} entries")
                content = _add_inline_citations(content, grounding_metadata)

        return content
    except asyncio.TimeoutError:
        logger.error(f"LLM call timed out after {timeout}s ({use_model})")
        return f"AI 调用超时，请稍后重试"
    except Exception as e:
        logger.error(f"LLM call failed ({use_model}): {e}")
        return f"AI 调用失败 ({use_model}): {e}"
