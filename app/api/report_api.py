"""投研周报 API - 仅 JSON 接口（前端 SPA: ReportPage.tsx）"""
import json
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import SessionLocal, WeeklyReport
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/report/versions")
async def list_versions(db: Session = Depends(_get_db)):
    """获取所有已完成报告的版本列表"""
    reports = (
        db.query(WeeklyReport)
        .filter(WeeklyReport.status == "completed")
        .order_by(WeeklyReport.version.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "version": r.version,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "model_name": r.model_name,
            "trigger": r.trigger,
        }
        for r in reports
    ]


@router.get("/api/report/{report_id}")
async def get_report(report_id: int, db: Session = Depends(_get_db)):
    """获取指定报告的完整数据"""
    report = db.query(WeeklyReport).filter(WeeklyReport.id == report_id).first()
    if not report:
        return {"error": "Report not found"}
    if report.status != "completed":
        return {"error": f"Report status is {report.status}"}

    return {
        "id": report.id,
        "version": report.version,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "model_name": report.model_name,
        "trigger": report.trigger,
        "market": {
            "indices": json.loads(report.index_data) if report.index_data else [],
            "ai_market_summary": report.ai_market_summary or "",
        },
        "capital": {
            "ai_capital_summary": report.ai_capital_summary or "",
        },
        "geopolitics": {
            "ai_geopolitics_summary": report.ai_geopolitics_summary or "",
        },
        "yield_curve": {
            "yield_curve": json.loads(report.yield_curve_data) if report.yield_curve_data else {},
            "ai_yield_curve_summary": report.ai_yield_curve_summary or "",
        },
        "x_monitor": {
            "x_tweets_data": json.loads(report.x_tweets_data) if getattr(report, "x_tweets_data", None) else {},
            "ai_x_monitor_summary": getattr(report, "ai_x_monitor_summary", None) or "",
        },
        "sector_strength": {
            "enhanced_sector_data": json.loads(report.enhanced_sector_data) if getattr(report, "enhanced_sector_data", None) else {},
            "ai_sector_strength_summary": getattr(report, "ai_sector_strength_summary", None) or "",
        },
        "sector": {
            "sectors": json.loads(report.sector_data) if report.sector_data else [],
            "ai_sector_summary": report.ai_sector_summary or "",
        },
        "stocks": {
            "watchlist_scores": json.loads(report.watchlist_scores) if report.watchlist_scores else [],
            "hot_stock_scores": json.loads(report.hot_stock_scores) if report.hot_stock_scores else [],
        },
    }


@router.get("/api/report/latest")
async def get_latest_report(db: Session = Depends(_get_db)):
    """获取最新一份已完成报告"""
    report = (
        db.query(WeeklyReport)
        .filter(WeeklyReport.status == "completed")
        .order_by(WeeklyReport.version.desc())
        .first()
    )
    if not report:
        return {"error": "No completed report available"}
    return await get_report(report.id, db=db)
