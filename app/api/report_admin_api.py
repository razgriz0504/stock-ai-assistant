"""投研周报管理 API - 报告版本管理 + Prompt 配置 + 定时任务（前端 SPA: ReportAdminPage.tsx）"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import SessionLocal, WeeklyReport, ReportConfig, User, UserPreference
from app.auth import get_current_user, require_admin
from app.report.weekly_report import (
    generate_full_report,
    get_or_create_report_config,
    DEFAULT_MARKET_SYSTEM_PROMPT,
    DEFAULT_CAPITAL_SYSTEM_PROMPT,
    DEFAULT_GEOPOLITICS_SYSTEM_PROMPT,
    DEFAULT_SECTOR_SYSTEM_PROMPT,
    DEFAULT_STOCKS_SYSTEM_PROMPT,
    DEFAULT_YIELD_CURVE_SYSTEM_PROMPT,
    DEFAULT_X_MONITOR_SYSTEM_PROMPT,
    DEFAULT_SECTOR_STRENGTH_SYSTEM_PROMPT,
)
from app.x_monitor.processor import DEFAULT_X_TWEET_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])

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
    capital_system_prompt: Optional[str] = None
    geopolitics_system_prompt: Optional[str] = None
    sector_system_prompt: Optional[str] = None
    stocks_system_prompt: Optional[str] = None
    yield_curve_system_prompt: Optional[str] = None
    x_tweet_system_prompt: Optional[str] = None
    x_monitor_system_prompt: Optional[str] = None
    sector_strength_system_prompt: Optional[str] = None


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    frequency: Optional[str] = None
    day_of_week: Optional[str] = None
    hour: Optional[int] = None
    minute: Optional[int] = None


# ─── API Endpoints ───

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
    current_user: User = Depends(get_current_user),
):
    """异步生成周报（返回 202 Accepted，前端轮询状态）"""
    # 解析 watchlist（未传入时默认取当前 admin 的）
    watchlist = req.watchlist
    if watchlist is None:
        pref = db.query(UserPreference).filter(
            UserPreference.user_id == current_user.id
        ).first()
        import json
        watchlist = json.loads(pref.watchlist) if pref and pref.watchlist else []

    # 先创建 DB 行拿到 report_id
    from app.report.weekly_report import _get_next_version, _resolve_prompts
    import json as _json

    config = get_or_create_report_config(db)
    (
        market_prompt,
        capital_prompt,
        geopolitics_prompt,
        sector_prompt,
        stocks_prompt,
        yield_curve_prompt,
        x_monitor_prompt,
        sector_strength_prompt,
    ) = _resolve_prompts(config)
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
        capital_system_prompt=capital_prompt,
        geopolitics_system_prompt=geopolitics_prompt,
        sector_system_prompt=sector_prompt,
        stocks_system_prompt=stocks_prompt,
        yield_curve_system_prompt=yield_curve_prompt,
        x_monitor_system_prompt=x_monitor_prompt,
        sector_strength_system_prompt=sector_strength_prompt,
        watchlist_used=_json.dumps(watchlist),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    # 后台任务执行实际生成
    background_tasks.add_task(
        _run_generate,
        report_id, watchlist,
        market_prompt, capital_prompt, geopolitics_prompt, sector_prompt,
        yield_curve_prompt, x_monitor_prompt, sector_strength_prompt,
    )

    return {"report_id": report_id, "version": version, "status": "running"}


async def _run_generate(
    report_id: int,
    watchlist: list[str],
    market_prompt: str,
    capital_prompt: str,
    geopolitics_prompt: str,
    sector_prompt: str,
    yield_curve_prompt: str,
    x_monitor_prompt: str,
    sector_strength_prompt: str,
):
    """后台任务：执行报告生成（与 generate_full_report 同步路径产物对齐）"""
    db = SessionLocal()
    try:
        report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
        if not report:
            return

        import asyncio
        import json
        from app.report.weekly_report import (
            fetch_index_data, fetch_sector_data, fetch_yield_curve_data,
            fetch_x_tweets_data,
            get_report_section_stocks,
            generate_ai_market_summary, generate_ai_capital_summary, generate_ai_geopolitics_summary, generate_ai_sector_summary,
            generate_ai_yield_curve_summary, generate_ai_x_monitor_summary,
            generate_ai_sector_strength_summary,
        )
        from app.data.sector_strength import fetch_enhanced_sector_data

        # 并行获取数据
        index_data, sector_data, stocks_data, curve_data, x_data, enhanced_sector_data = await asyncio.gather(
            asyncio.to_thread(fetch_index_data),
            asyncio.to_thread(fetch_sector_data),
            get_report_section_stocks(watchlist),
            asyncio.to_thread(fetch_yield_curve_data),
            asyncio.to_thread(fetch_x_tweets_data, db, 7),
            asyncio.to_thread(fetch_enhanced_sector_data, False),
        )

        # AI 分析
        (
            ai_market_summary,
            ai_capital_summary,
            ai_geopolitics_summary,
            ai_sector_summary,
            ai_yield_curve_summary,
            ai_x_monitor_summary,
            ai_sector_strength_summary,
        ) = await asyncio.gather(
            generate_ai_market_summary(index_data, system_prompt=market_prompt),
            generate_ai_capital_summary(system_prompt=capital_prompt),
            generate_ai_geopolitics_summary(system_prompt=geopolitics_prompt),
            generate_ai_sector_summary(sector_data, system_prompt=sector_prompt),
            generate_ai_yield_curve_summary(curve_data, system_prompt=yield_curve_prompt),
            generate_ai_x_monitor_summary(x_data, system_prompt=x_monitor_prompt),
            generate_ai_sector_strength_summary(enhanced_sector_data, system_prompt=sector_strength_prompt),
        )

        # 序列化写入 DB
        report.index_data = json.dumps(index_data, ensure_ascii=False)
        report.sector_data = json.dumps(sector_data, ensure_ascii=False)
        report.watchlist_scores = json.dumps(stocks_data.get("watchlist_scores", []), ensure_ascii=False)
        report.hot_stock_scores = json.dumps(stocks_data.get("hot_stock_scores", []), ensure_ascii=False)
        report.yield_curve_data = json.dumps(curve_data, ensure_ascii=False)
        report.x_tweets_data = json.dumps(x_data, ensure_ascii=False)
        report.enhanced_sector_data = json.dumps(enhanced_sector_data, ensure_ascii=False)
        report.ai_market_summary = ai_market_summary
        report.ai_capital_summary = ai_capital_summary
        report.ai_geopolitics_summary = ai_geopolitics_summary
        report.ai_sector_summary = ai_sector_summary
        report.ai_yield_curve_summary = ai_yield_curve_summary
        report.ai_x_monitor_summary = ai_x_monitor_summary
        report.ai_sector_strength_summary = ai_sector_strength_summary
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


@router.delete("/api/admin/reports/{report_id}")
async def delete_report(report_id: int, db: Session = Depends(_get_db)):
    """删除指定报告"""
    report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
    if not report:
        return {"error": "Report not found"}
    db.delete(report)
    db.commit()
    return {"success": True}


@router.get("/api/admin/prompts")
async def get_prompts(db: Session = Depends(_get_db)):
    """获取 Prompt 配置"""
    config = get_or_create_report_config(db)
    return {
        "market_system_prompt": config.default_market_system_prompt or DEFAULT_MARKET_SYSTEM_PROMPT,
        "capital_system_prompt": config.default_capital_system_prompt or DEFAULT_CAPITAL_SYSTEM_PROMPT,
        "geopolitics_system_prompt": config.default_geopolitics_system_prompt or DEFAULT_GEOPOLITICS_SYSTEM_PROMPT,
        "sector_system_prompt": config.default_sector_system_prompt or DEFAULT_SECTOR_SYSTEM_PROMPT,
        "stocks_system_prompt": config.default_stocks_system_prompt or DEFAULT_STOCKS_SYSTEM_PROMPT,
        "yield_curve_system_prompt": getattr(config, "default_yield_curve_system_prompt", None) or DEFAULT_YIELD_CURVE_SYSTEM_PROMPT,
        "x_tweet_system_prompt": getattr(config, "default_x_tweet_system_prompt", None) or DEFAULT_X_TWEET_SYSTEM_PROMPT,
        "x_monitor_system_prompt": getattr(config, "default_x_monitor_system_prompt", None) or DEFAULT_X_MONITOR_SYSTEM_PROMPT,
        "sector_strength_system_prompt": getattr(config, "default_sector_strength_system_prompt", None) or DEFAULT_SECTOR_STRENGTH_SYSTEM_PROMPT,
        "defaults": {
            "market_system_prompt": DEFAULT_MARKET_SYSTEM_PROMPT,
            "capital_system_prompt": DEFAULT_CAPITAL_SYSTEM_PROMPT,
            "geopolitics_system_prompt": DEFAULT_GEOPOLITICS_SYSTEM_PROMPT,
            "sector_system_prompt": DEFAULT_SECTOR_SYSTEM_PROMPT,
            "stocks_system_prompt": DEFAULT_STOCKS_SYSTEM_PROMPT,
            "yield_curve_system_prompt": DEFAULT_YIELD_CURVE_SYSTEM_PROMPT,
            "x_tweet_system_prompt": DEFAULT_X_TWEET_SYSTEM_PROMPT,
            "x_monitor_system_prompt": DEFAULT_X_MONITOR_SYSTEM_PROMPT,
            "sector_strength_system_prompt": DEFAULT_SECTOR_STRENGTH_SYSTEM_PROMPT,
        },
    }


@router.post("/api/admin/prompts")
async def update_prompts(req: PromptsUpdate, db: Session = Depends(_get_db)):
    """更新 Prompt 配置"""
    config = get_or_create_report_config(db)
    if req.market_system_prompt is not None:
        config.default_market_system_prompt = req.market_system_prompt
    if req.capital_system_prompt is not None:
        config.default_capital_system_prompt = req.capital_system_prompt
    if req.geopolitics_system_prompt is not None:
        config.default_geopolitics_system_prompt = req.geopolitics_system_prompt
    if req.sector_system_prompt is not None:
        config.default_sector_system_prompt = req.sector_system_prompt
    if req.stocks_system_prompt is not None:
        config.default_stocks_system_prompt = req.stocks_system_prompt
    if req.yield_curve_system_prompt is not None:
        config.default_yield_curve_system_prompt = req.yield_curve_system_prompt
    if req.x_tweet_system_prompt is not None:
        config.default_x_tweet_system_prompt = req.x_tweet_system_prompt
    if req.x_monitor_system_prompt is not None:
        config.default_x_monitor_system_prompt = req.x_monitor_system_prompt
    if req.sector_strength_system_prompt is not None:
        config.default_sector_strength_system_prompt = req.sector_strength_system_prompt
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
