"""APScheduler X 监控作业入口

每隔 N 小时调用一次：拉取所有启用账号的最新推文 → 入库 → 触发 AI 处理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.x_monitor.client import (
    XAPIError,
    fetch_user_tweets,
    get_user_id_by_username,
)
from app.x_monitor.processor import process_pending_tweets
from db.models import ReportConfig, SessionLocal, XAccount, XTweet

logger = logging.getLogger(__name__)


def _resolve_bearer(config: ReportConfig) -> str:
    """优先环境变量，其次 DB"""
    env_token = os.getenv("X_API_BEARER_TOKEN", "").strip()
    if env_token:
        return env_token
    return (config.x_api_bearer_token or "").strip()


def _resolve_tweet_prompt(config: ReportConfig) -> str:
    return (getattr(config, "default_x_tweet_system_prompt", "") or "").strip()


async def run_x_monitor_job(force_process: bool = True) -> dict:
    """完整一轮抓取 + AI 处理。

    返回 {accounts_total, tweets_added, processed, failed, errors[]}
    """
    db: Session = SessionLocal()
    summary: dict = {
        "accounts_total": 0,
        "tweets_added": 0,
        "processed": 0,
        "failed": 0,
        "errors": [],
    }
    try:
        config = db.query(ReportConfig).filter_by(id=1).first()
        if config is None:
            logger.warning("ReportConfig 不存在，跳过 X 监控作业")
            return summary
        bearer = _resolve_bearer(config)
        if not bearer:
            logger.info("X Bearer Token 未配置，跳过监控作业")
            summary["errors"].append("Bearer Token 未配置")
            return summary

        accounts = db.query(XAccount).filter_by(enabled=True).all()
        summary["accounts_total"] = len(accounts)

        for acc in accounts:
            try:
                added = await asyncio.to_thread(_fetch_one_account, db, bearer, acc)
                summary["tweets_added"] += added
            except XAPIError as exc:
                logger.warning("X API 错误 @%s: %s", acc.username, exc)
                summary["errors"].append(f"@{acc.username}: {exc}")
            except Exception as exc:  # pragma: no cover
                logger.exception("抓取 @%s 失败", acc.username)
                summary["errors"].append(f"@{acc.username}: {exc}")

        if force_process:
            tweet_prompt = _resolve_tweet_prompt(config)
            ai = await process_pending_tweets(db, system_prompt=tweet_prompt)
            summary["processed"] = ai.get("processed", 0)
            summary["failed"] = ai.get("failed", 0)
        return summary
    finally:
        db.close()


def _fetch_one_account(db: Session, bearer: str, acc: XAccount) -> int:
    """同步抓取单个账号，写入 x_tweets。返回新增条数。"""
    # 若没有 x_user_id，先解析
    if not acc.x_user_id:
        info = get_user_id_by_username(acc.username, bearer)
        acc.x_user_id = info["id"]
        if not acc.display_name:
            acc.display_name = info.get("name", "") or acc.display_name
        db.commit()

    tweets = fetch_user_tweets(
        user_id=acc.x_user_id,
        bearer=bearer,
        since_id=acc.last_tweet_id or "",
        max_results=20,
    )
    if not tweets:
        acc.last_fetched_at = datetime.now(timezone.utc)
        db.commit()
        return 0

    added = 0
    max_id = acc.last_tweet_id or ""
    for t in tweets:
        # 可能由于并发抓取重复，唯一索引会保护我们；这里先查
        exists = db.query(XTweet).filter_by(tweet_id=t["tweet_id"]).first()
        if exists is not None:
            if not max_id or _id_gt(t["tweet_id"], max_id):
                max_id = t["tweet_id"]
            continue
        db.add(XTweet(
            tweet_id=t["tweet_id"],
            account_id=acc.id,
            username=acc.username,
            text=t["text"],
            metrics=json.dumps(t.get("metrics", {}), ensure_ascii=False),
            created_at_x=t["created_at"],
            processed=False,
        ))
        added += 1
        if not max_id or _id_gt(t["tweet_id"], max_id):
            max_id = t["tweet_id"]

    if max_id:
        acc.last_tweet_id = max_id
    acc.last_fetched_at = datetime.now(timezone.utc)
    db.commit()
    return added


def _id_gt(a: str, b: str) -> bool:
    """X tweet_id 是单调递增的 snowflake id，比较时用整数"""
    try:
        return int(a) > int(b)
    except ValueError:
        return a > b
