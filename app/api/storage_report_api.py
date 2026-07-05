"""存储行业研究报告 REST API（前端 SPA: StorageReportPage.tsx）

数据源统一为 Gemini 联网搜索。覆盖六大能力 + 版本化报告管理 + Prompt/调度配置。
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from db.models import SessionLocal, StorageReport, StorageReportConfig
from app.storage_report.constants import CATEGORIES, THEMES, VENDORS, METRIC_DICT
from app.storage_report import analyzer
from app.storage_report.analyzer import (
    get_or_create_storage_config,
    resolve_prompts,
    _get_next_version,
)
from app.storage_report.prompts import (
    DEFAULT_METRIC_PROMPT,
    DEFAULT_PROSPERITY_PROMPT,
    DEFAULT_PRICE_TREND_PROMPT,
    DEFAULT_SUPPLY_DEMAND_PROMPT,
    DEFAULT_VENDOR_PROMPT,
    DEFAULT_ANOMALY_PROMPT,
)
from app.llm.client import get_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/storage-report", tags=["storage-report"])


# ═══════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════

class MetricQueryRequest(BaseModel):
    metric_key: str
    category: str = ""


class ProsperityRequest(BaseModel):
    time_range: str = "近3个月"
    categories: list[str] = []
    themes: list[str] = []


class PriceTrendRequest(BaseModel):
    categories: list[str] = []
    time_range: str = "近3个月"


class SupplyDemandRequest(BaseModel):
    category: str = "DRAM"
    time_range: str = "近3个月"


class VendorTrackingRequest(BaseModel):
    vendors: list[str] = []


class AnomalyRequest(BaseModel):
    time_range: str = "近3个月"


class GenerateRequest(BaseModel):
    categories: Optional[list[str]] = None
    time_range: str = "近3个月"


class ConfigUpdate(BaseModel):
    schedule_enabled: Optional[bool] = None
    schedule_day_of_week: Optional[str] = None
    schedule_hour: Optional[int] = None
    schedule_minute: Optional[int] = None
    default_categories: Optional[list[str]] = None
    metric_system_prompt: Optional[str] = None
    prosperity_system_prompt: Optional[str] = None
    price_trend_system_prompt: Optional[str] = None
    supply_demand_system_prompt: Optional[str] = None
    vendor_system_prompt: Optional[str] = None
    anomaly_system_prompt: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# 元数据 / 口径字典
# ═══════════════════════════════════════════════════════════════

@router.get("/metrics")
async def get_metrics():
    """返回品类、主题、厂商、指标口径字典（供前端下拉与说明）"""
    return {
        "categories": CATEGORIES,
        "themes": THEMES,
        "vendors": VENDORS,
        "metrics": METRIC_DICT,
    }


# ═══════════════════════════════════════════════════════════════
# 六大能力（即时分析）
# ═══════════════════════════════════════════════════════════════

@router.post("/metric-query")
async def metric_query(req: MetricQueryRequest):
    """指标查询与口径解释"""
    return await analyzer.query_metric(req.metric_key, req.category)


@router.post("/prosperity")
async def prosperity(req: ProsperityRequest):
    """行业景气度综合研判"""
    return await analyzer.analyze_prosperity(req.time_range, req.categories, req.themes)


@router.post("/price-trend")
async def price_trend(req: PriceTrendRequest):
    """价格趋势分析"""
    return await analyzer.analyze_price_trend(req.categories, req.time_range)


@router.post("/supply-demand")
async def supply_demand(req: SupplyDemandRequest):
    """供需归因分析"""
    content = await analyzer.analyze_supply_demand(req.category, req.time_range)
    return {"category": req.category, "time_range": req.time_range, "content": content}


@router.post("/vendor-tracking")
async def vendor_tracking(req: VendorTrackingRequest):
    """厂商动态追踪"""
    content = await analyzer.track_vendors(req.vendors)
    return {"vendors": req.vendors, "content": content}


@router.post("/anomaly")
async def anomaly(req: AnomalyRequest):
    """景气度异动识别"""
    return await analyzer.detect_anomaly(req.time_range)


# ═══════════════════════════════════════════════════════════════
# 一键生成完整版本化报告（后台任务 + 轮询）
# ═══════════════════════════════════════════════════════════════

def _run_generate(report_id: int, categories: list[str], time_range: str):
    """后台任务包装：新建独立事件循环执行 async 生成"""
    import asyncio
    db = SessionLocal()
    try:
        asyncio.run(
            analyzer.generate_full_report(
                db, categories=categories, time_range=time_range,
                trigger="manual", report_id=report_id,
            )
        )
    except Exception as e:
        logger.error(f"Background storage report failed (id={report_id}): {e}", exc_info=True)
        try:
            report = db.query(StorageReport).filter_by(id=report_id).first()
            if report:
                report.status = "failed"
                report.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/generate", status_code=202)
async def start_generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """异步生成完整报告（返回 202，前端轮询 /status/{id}）"""
    db = SessionLocal()
    try:
        config = get_or_create_storage_config(db)
        prompts = resolve_prompts(config)
        cats = req.categories or json.loads(config.default_categories or '["DRAM","NAND","HBM"]')
        version = _get_next_version(db)
        report = StorageReport(
            version=version,
            report_date=datetime.now(timezone.utc),
            status="running",
            trigger="manual",
            model_name=get_model(),
            categories=json.dumps(cats, ensure_ascii=False),
            time_range=req.time_range,
            prosperity_system_prompt=prompts["prosperity"],
            price_trend_system_prompt=prompts["price_trend"],
            supply_demand_system_prompt=prompts["supply_demand"],
            vendor_system_prompt=prompts["vendor"],
            anomaly_system_prompt=prompts["anomaly"],
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        report_id = report.id
    finally:
        db.close()

    background_tasks.add_task(_run_generate, report_id, cats, req.time_range)
    return {"report_id": report_id, "version": version, "status": "running"}


@router.get("/status/{report_id}")
async def get_status(report_id: int):
    """轮询报告生成状态"""
    db = SessionLocal()
    try:
        report = db.query(StorageReport).filter_by(id=report_id).first()
        if not report:
            raise HTTPException(404, "Report not found")
        return {
            "id": report.id,
            "version": report.version,
            "status": report.status,
            "error_message": report.error_message,
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 报告版本管理
# ═══════════════════════════════════════════════════════════════

@router.get("/reports")
async def list_reports(limit: int = 50):
    """列出报告版本"""
    db = SessionLocal()
    try:
        reports = db.query(StorageReport).order_by(
            StorageReport.version.desc()
        ).limit(limit).all()
        return [
            {
                "id": r.id,
                "version": r.version,
                "status": r.status,
                "trigger": r.trigger,
                "model_name": r.model_name,
                "categories": json.loads(r.categories) if r.categories else [],
                "time_range": r.time_range,
                "report_date": r.report_date.isoformat() if r.report_date else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    finally:
        db.close()


def _parse_json(s: str, fallback):
    try:
        return json.loads(s) if s else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


@router.get("/report/{report_id}")
async def get_report(report_id: int):
    """获取单个报告详情"""
    db = SessionLocal()
    try:
        r = db.query(StorageReport).filter_by(id=report_id).first()
        if not r:
            raise HTTPException(404, "Report not found")
        return {
            "id": r.id,
            "version": r.version,
            "status": r.status,
            "trigger": r.trigger,
            "model_name": r.model_name,
            "categories": _parse_json(r.categories, []),
            "time_range": r.time_range,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "prosperity": _parse_json(r.prosperity_data, {}),
            "price_trend": _parse_json(r.price_trend_data, {}),
            "supply_demand": r.supply_demand_data or "",
            "vendor": r.vendor_data or "",
            "anomaly": _parse_json(r.anomaly_data, {}),
            "error_message": r.error_message,
        }
    finally:
        db.close()


@router.delete("/report/{report_id}")
async def delete_report(report_id: int):
    """删除指定报告"""
    db = SessionLocal()
    try:
        r = db.query(StorageReport).filter_by(id=report_id).first()
        if not r:
            raise HTTPException(404, "Report not found")
        db.delete(r)
        db.commit()
        return {"success": True}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Prompt / 调度配置
# ═══════════════════════════════════════════════════════════════

@router.get("/config")
async def get_config():
    """获取 Prompt 与调度配置"""
    db = SessionLocal()
    try:
        c = get_or_create_storage_config(db)
        return {
            "schedule_enabled": c.schedule_enabled,
            "schedule_day_of_week": c.schedule_day_of_week,
            "schedule_hour": c.schedule_hour,
            "schedule_minute": c.schedule_minute,
            "default_categories": _parse_json(c.default_categories, ["DRAM", "NAND", "HBM"]),
            "metric_system_prompt": c.default_metric_system_prompt or DEFAULT_METRIC_PROMPT,
            "prosperity_system_prompt": c.default_prosperity_system_prompt or DEFAULT_PROSPERITY_PROMPT,
            "price_trend_system_prompt": c.default_price_trend_system_prompt or DEFAULT_PRICE_TREND_PROMPT,
            "supply_demand_system_prompt": c.default_supply_demand_system_prompt or DEFAULT_SUPPLY_DEMAND_PROMPT,
            "vendor_system_prompt": c.default_vendor_system_prompt or DEFAULT_VENDOR_PROMPT,
            "anomaly_system_prompt": c.default_anomaly_system_prompt or DEFAULT_ANOMALY_PROMPT,
            "defaults": {
                "metric_system_prompt": DEFAULT_METRIC_PROMPT,
                "prosperity_system_prompt": DEFAULT_PROSPERITY_PROMPT,
                "price_trend_system_prompt": DEFAULT_PRICE_TREND_PROMPT,
                "supply_demand_system_prompt": DEFAULT_SUPPLY_DEMAND_PROMPT,
                "vendor_system_prompt": DEFAULT_VENDOR_PROMPT,
                "anomaly_system_prompt": DEFAULT_ANOMALY_PROMPT,
            },
        }
    finally:
        db.close()


@router.post("/config")
async def update_config(req: ConfigUpdate):
    """更新 Prompt 与调度配置，并同步调度器"""
    db = SessionLocal()
    try:
        c = get_or_create_storage_config(db)
        if req.schedule_enabled is not None:
            c.schedule_enabled = req.schedule_enabled
        if req.schedule_day_of_week is not None:
            c.schedule_day_of_week = req.schedule_day_of_week
        if req.schedule_hour is not None:
            c.schedule_hour = req.schedule_hour
        if req.schedule_minute is not None:
            c.schedule_minute = req.schedule_minute
        if req.default_categories is not None:
            c.default_categories = json.dumps(req.default_categories, ensure_ascii=False)
        if req.metric_system_prompt is not None:
            c.default_metric_system_prompt = req.metric_system_prompt
        if req.prosperity_system_prompt is not None:
            c.default_prosperity_system_prompt = req.prosperity_system_prompt
        if req.price_trend_system_prompt is not None:
            c.default_price_trend_system_prompt = req.price_trend_system_prompt
        if req.supply_demand_system_prompt is not None:
            c.default_supply_demand_system_prompt = req.supply_demand_system_prompt
        if req.vendor_system_prompt is not None:
            c.default_vendor_system_prompt = req.vendor_system_prompt
        if req.anomaly_system_prompt is not None:
            c.default_anomaly_system_prompt = req.anomaly_system_prompt
        db.commit()
        db.refresh(c)

        # 同步调度器
        try:
            from app.monitor.scheduler import (
                add_storage_report_job, remove_storage_report_job,
            )
            if c.schedule_enabled:
                add_storage_report_job(
                    day_of_week=c.schedule_day_of_week,
                    hour=c.schedule_hour,
                    minute=c.schedule_minute,
                )
            else:
                remove_storage_report_job()
        except Exception as e:
            logger.error(f"Failed to sync storage report scheduler: {e}")

        return {"success": True}
    finally:
        db.close()
