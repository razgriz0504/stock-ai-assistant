"""X 推文 AI 处理器：翻译 / 总结要点 / 情绪 / 市场影响评估"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.llm.client import chat
from db.models import XTweet

logger = logging.getLogger(__name__)


DEFAULT_X_TWEET_SYSTEM_PROMPT = """你是一名专业的金融市场分析师，专精于解读社交媒体上的重要言论对股票市场的影响。

对用户给出的英文推文，输出严格的 JSON（不要 markdown 代码块、不要解释文字、不要前后缀）：

{
  "text_zh": "中文翻译（自然准确，保留专有名词）",
  "key_points": ["要点1", "要点2"],
  "sentiment": "bullish|bearish|neutral",
  "impact_assets": ["SPY","TLT"],
  "market_impact": "1-2 句中文市场影响评述，说明对哪些资产/行业可能产生何种影响"
}

要求：
1. text_zh 必填；key_points 1-3 条简短中文要点
2. sentiment 严格三选一（看涨/看跌/中性 → bullish/bearish/neutral）
3. impact_assets 列出受影响的标准 ticker（如 SPY, QQQ, TLT, GLD, BTC, TSLA, AAPL 等），无明显标的则返回 []
4. 仅返回单一 JSON 对象，必须可被 json.loads 解析"""


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # 去掉首尾 ``` 块
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _extract_json(s: str) -> dict | None:
    """容错地从 LLM 输出中抽取 JSON 对象"""
    s = _strip_code_fence(s)
    # 尝试直接解析
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # 抓取第一个花括号块
    match = re.search(r"\{.*\}", s, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize(parsed: dict | None, raw_text: str) -> dict:
    """将 LLM 解析结果规范化为标准结构，缺字段使用兜底值"""
    if not isinstance(parsed, dict):
        parsed = {}
    sentiment = str(parsed.get("sentiment", "")).lower().strip()
    if sentiment not in ("bullish", "bearish", "neutral"):
        sentiment = "neutral"
    impact_assets = parsed.get("impact_assets") or []
    if not isinstance(impact_assets, list):
        impact_assets = []
    impact_assets = [str(a).upper().strip() for a in impact_assets if str(a).strip()]
    key_points = parsed.get("key_points") or []
    if not isinstance(key_points, list):
        key_points = []
    key_points = [str(p).strip() for p in key_points if str(p).strip()]
    return {
        "text_zh": str(parsed.get("text_zh") or raw_text).strip(),
        "key_points": key_points,
        "sentiment": sentiment,
        "impact_assets": impact_assets,
        "market_impact": str(parsed.get("market_impact") or "").strip(),
    }


async def process_tweet(tweet_text: str, system_prompt: str = "") -> dict:
    """对单条推文调用 LLM 输出结构化结果"""
    sys_prompt = (system_prompt or DEFAULT_X_TWEET_SYSTEM_PROMPT).strip()
    if not tweet_text or not tweet_text.strip():
        return _normalize(None, tweet_text)
    try:
        raw = await chat(prompt=tweet_text.strip(), system_prompt=sys_prompt)
    except Exception as exc:
        logger.warning("LLM 调用失败 (tweet=%r): %s", tweet_text[:60], exc)
        return _normalize(None, tweet_text)
    parsed = _extract_json(raw)
    return _normalize(parsed, tweet_text)


async def process_pending_tweets(
    db: Session,
    system_prompt: str = "",
    max_concurrent: int = 3,
    limit: int = 100,
) -> dict:
    """批量处理 processed=False 的推文，限制并发

    返回 {processed, failed}
    """
    pending: list[XTweet] = (
        db.query(XTweet)
        .filter(XTweet.processed == False)  # noqa: E712
        .order_by(XTweet.created_at_x.asc())
        .limit(limit)
        .all()
    )
    if not pending:
        return {"processed": 0, "failed": 0}

    sem = asyncio.Semaphore(max(1, max_concurrent))
    results: list[tuple[int, dict | Exception]] = []

    async def _one(tw: XTweet):
        async with sem:
            try:
                out = await process_tweet(tw.text or "", system_prompt)
                results.append((tw.id, out))
            except Exception as exc:  # pragma: no cover - 防御
                results.append((tw.id, exc))

    await asyncio.gather(*[_one(t) for t in pending])

    processed = 0
    failed = 0
    by_id = {r[0]: r[1] for r in results}
    for tw in pending:
        result = by_id.get(tw.id)
        if isinstance(result, Exception):
            tw.processing_error = str(result)[:500]
            tw.processed = False
            failed += 1
            continue
        out: dict[str, Any] = result if isinstance(result, dict) else {}
        tw.text_zh = out.get("text_zh", "")
        tw.key_points = json.dumps(out.get("key_points", []), ensure_ascii=False)
        tw.sentiment = out.get("sentiment", "neutral")
        tw.impact_assets = json.dumps(out.get("impact_assets", []), ensure_ascii=False)
        tw.market_impact = out.get("market_impact", "")
        tw.processed = True
        tw.processing_error = ""
        processed += 1
    db.commit()
    return {"processed": processed, "failed": failed}
