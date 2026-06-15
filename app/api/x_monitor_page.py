"""X (Twitter) 关键账号舆情监控 REST API（前端 SPA: XMonitorPage.tsx）"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
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
