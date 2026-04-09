import os
import logging
from litellm import completion

from config import settings

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = {
    "gemini": "gemini/gemini-2.0-flash",
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


async def chat(prompt: str, system_prompt: str = "", model: str = "") -> str:
    use_model = model or _current_model
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        logger.info(f"Calling LLM: {use_model}")
        kwargs = {"model": use_model, "messages": messages}

        if use_model in _CUSTOM_API_BASE:
            kwargs["api_base"] = _CUSTOM_API_BASE[use_model]
        if use_model in _CUSTOM_API_KEY:
            kwargs["api_key"] = os.environ.get(_CUSTOM_API_KEY[use_model], "")

        response = completion(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM call failed ({use_model}): {e}")
        return f"AI 调用失败 ({use_model}): {e}"
