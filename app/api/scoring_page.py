"""投研周报页面 - 版本选择 + 只读查看 + PDF 导出"""
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from db.models import SessionLocal, WeeklyReport

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/scoring", response_class=HTMLResponse)
async def scoring_page():
    return _build_html()


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


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投研周报</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #faf9f5; color: #1a1a1a; font-family: 'DM Sans', -apple-system, sans-serif; min-height: 100vh; }

.page-wrap { max-width: 1100px; margin: 0 auto; padding: 40px 32px; }
.head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid #e8e4de; }
.head-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; color: #c9774a; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.head-label::before { content: ''; display: inline-block; width: 6px; height: 6px; background: #c9774a; border-radius: 50%; }
.head h1 { font-family: 'Space Grotesk', sans-serif; font-size: 32px; font-weight: 700; margin: 0; }
.head h1 span { color: #c9774a; }
.head-date { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #6b6560; margin-top: 8px; }
.head-right { display: flex; align-items: center; gap: 12px; }

/* Buttons */
.btn { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px 16px; border-radius: 6px; border: 1px solid #d4cfc7; background: #fff; color: #1a1a1a; cursor: pointer; transition: all .15s; }
.btn:hover { border-color: #c9774a; color: #c9774a; }
.btn-primary { background: #c9774a; color: #fff; border-color: #c9774a; }
.btn-primary:hover { background: #b5683e; border-color: #b5683e; color: #fff; }

/* Version selector */
.ver-select { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px 12px; border-radius: 6px; border: 1px solid #d4cfc7; background: #fff; color: #1a1a1a; cursor: pointer; min-width: 160px; }
.ver-select:focus { outline: none; border-color: #c9774a; }

/* Section headers */
.sec-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 24px; }
.sec-num { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #c9774a; letter-spacing: 1px; }
.sec-title { font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: 600; }
.sec-sub { font-size: 13px; color: #6b6560; margin-left: auto; }

/* Index Cards */
.idx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.idx-card { background: #fff; padding: 24px; border: 1px solid #e8e4de; border-radius: 10px; position: relative; }
.idx-card:hover { border-color: #c9774a; }
.idx-name { font-family: 'Space Grotesk', sans-serif; font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.idx-symbol { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a8a29e; margin-bottom: 16px; }
.idx-price { font-family: 'Space Grotesk', sans-serif; font-size: 28px; font-weight: 700; letter-spacing: -1px; margin-bottom: 8px; }
.idx-change { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500; }
.idx-change.up { color: #2d6a4f; }
.idx-change.down { color: #b91c1c; }
.idx-change-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #a8a29e; margin-top: 4px; }

/* AI Summary */
.ai-box { position: relative; padding: 20px 20px 20px 28px; background: #fff; border: 1px solid #e8e4de; border-radius: 10px; }
.ai-box::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #c9774a; border-radius: 2px 0 0 2px; }
.ai-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #c9774a; margin-bottom: 10px; }
.ai-text { font-size: 14px; line-height: 1.8; color: #44403c; }
.ai-text p { margin: 0 0 8px 0; }
.ai-text p:last-child { margin-bottom: 0; }
.ai-text strong { font-weight: 700; color: #1a1a1a; }
.ai-text h3 { font-family: 'Space Grotesk', sans-serif; font-size: 15px; font-weight: 600; margin: 12px 0 6px 0; color: #1a1a1a; }
.ai-text h4 { font-family: 'Space Grotesk', sans-serif; font-size: 14px; font-weight: 600; margin: 10px 0 4px 0; color: #1a1a1a; }
.ai-text ul, .ai-text ol { padding-left: 20px; margin: 4px 0; }
.ai-text li { margin: 2px 0; }
.ai-text em { color: #6b6560; }
.ai-text .katex { font-size: 1em; }
.ai-text .katex-display { margin: 8px 0; overflow-x: auto; }

/* Yield Curve */
.yc-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
.yc-card { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 20px; }
.yc-regime { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.yc-regime-badge { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px; letter-spacing: 0.5px; text-transform: uppercase; }
.yc-regime-badge.bear-steepener { background: rgba(185,28,28,0.08); color: #b91c1c; }
.yc-regime-badge.bear-flattener { background: rgba(180,83,9,0.10); color: #b45309; }
.yc-regime-badge.bull-steepener { background: rgba(45,106,79,0.10); color: #2d6a4f; }
.yc-regime-badge.bull-flattener { background: rgba(124,58,237,0.10); color: #7c3aed; }
.yc-regime-badge.mixed { background: rgba(168,162,158,0.20); color: #6b6560; }
.yc-regime-logic { font-size: 13px; color: #44403c; line-height: 1.6; }
.yc-yields-tbl { width: 100%; border-collapse: collapse; }
.yc-yields-tbl th { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: #6b6560; padding: 8px 6px; text-align: left; border-bottom: 1px solid #e8e4de; font-weight: 500; }
.yc-yields-tbl td { padding: 8px 6px; border-bottom: 1px solid #f5f3ef; font-size: 13px; }
.yc-yields-tbl tr:last-child td { border-bottom: none; }
.yc-tenor { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
.yc-yield { font-family: 'JetBrains Mono', monospace; font-weight: 500; }
.yc-bp { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.yc-bp.up { color: #b91c1c; }
.yc-bp.down { color: #2d6a4f; }
.yc-bp.flat { color: #a8a29e; }
.yc-spreads { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
.yc-spread-item { background: #faf9f5; border: 1px solid #e8e4de; border-radius: 6px; padding: 10px 12px; }
.yc-spread-name { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #6b6560; letter-spacing: 1px; margin-bottom: 4px; }
.yc-spread-val { font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: 700; }
.yc-spread-chg { font-family: 'JetBrains Mono', monospace; font-size: 11px; margin-top: 2px; }
.yc-cross { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 12px; }
.yc-cross-item { background: #faf9f5; border: 1px solid #e8e4de; border-radius: 6px; padding: 8px 10px; text-align: center; }
.yc-cross-name { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #6b6560; letter-spacing: 0.5px; margin-bottom: 4px; }
.yc-cross-val { font-family: 'Space Grotesk', sans-serif; font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.yc-cross-chg { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
@media (max-width: 700px) { .yc-grid { grid-template-columns: 1fr; } .yc-cross { grid-template-columns: repeat(3, 1fr); } .yc-spreads { grid-template-columns: 1fr; } }

/* X Monitor */
.xm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.xm-card { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 20px; }
.xm-card-title { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #6b6560; margin-bottom: 14px; }
.xm-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.xm-stat { text-align: center; padding: 10px; background: #faf9f5; border-radius: 6px; }
.xm-stat-val { font-family: 'Space Grotesk', sans-serif; font-size: 20px; font-weight: 700; }
.xm-stat-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; color: #6b6560; margin-top: 4px; text-transform: uppercase; }
.xm-sentiment-bullish { color: #2d6a4f; }
.xm-sentiment-bearish { color: #b91c1c; }
.xm-sentiment-neutral { color: #6b6560; }
.xm-asset-list { display: flex; flex-wrap: wrap; gap: 6px; }
.xm-asset-tag { font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 3px 8px; border-radius: 4px; background: #faf9f5; border: 1px solid #e8e4de; color: #44403c; }
.xm-asset-tag b { color: #c9774a; margin-left: 4px; }
.xm-tweet-list { display: flex; flex-direction: column; gap: 12px; }
.xm-tweet-card { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 16px 18px; }
.xm-tweet-card:hover { border-color: #c9774a; }
.xm-tweet-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 10px; }
.xm-tweet-user { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 14px; color: #1a1a1a; }
.xm-tweet-user::before { content: '@'; color: #a8a29e; margin-right: 1px; }
.xm-tweet-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a8a29e; display: flex; gap: 10px; align-items: center; }
.xm-sentiment-pill { font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 2px 8px; border-radius: 10px; text-transform: uppercase; letter-spacing: 1px; }
.xm-sentiment-pill.bullish { background: #d8e9df; color: #2d6a4f; }
.xm-sentiment-pill.bearish { background: #f5d7d7; color: #b91c1c; }
.xm-sentiment-pill.neutral { background: #ece9e2; color: #6b6560; }
.xm-tweet-text { font-size: 13px; line-height: 1.7; color: #6b6560; margin-bottom: 6px; font-style: italic; }
.xm-tweet-zh { font-size: 14px; line-height: 1.7; color: #1a1a1a; margin-bottom: 8px; }
.xm-tweet-impact { font-size: 12px; color: #44403c; padding: 8px 10px; background: #faf9f5; border-radius: 6px; margin-top: 8px; }
.xm-tweet-assets { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.xm-empty { padding: 30px; text-align: center; color: #a8a29e; font-size: 13px; background: #fff; border: 1px solid #e8e4de; border-radius: 10px; }
@media (max-width: 700px) { .xm-grid { grid-template-columns: 1fr; } .xm-stats { grid-template-columns: repeat(3, 1fr); } }

/* Sector Table */
.sector-tbl { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e8e4de; border-radius: 10px; overflow: hidden; }
.sector-tbl th { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: #6b6560; padding: 14px 16px; text-align: left; border-bottom: 1px solid #e8e4de; font-weight: 500; background: #faf9f5; }
.sector-tbl td { padding: 12px 16px; border-bottom: 1px solid #f0ece6; font-size: 13px; }
.sector-tbl tr:last-child td { border-bottom: none; }
.sector-tbl tbody tr:hover { background: #faf9f5; }
.sector-name { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 14px; }
.sector-etf { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a8a29e; margin-left: 8px; }
.chg { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500; }
.chg.up { color: #2d6a4f; }
.chg.down { color: #b91c1c; }
.chg.flat { color: #a8a29e; }

/* Stock Cards */
.stock-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stock-card { background: #fff; border: 1px solid #e8e4de; border-radius: 10px; padding: 20px; }
.stock-card:hover { border-color: #c9774a; }
.stock-card-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.stock-sym { font-family: 'Space Grotesk', sans-serif; font-size: 16px; font-weight: 700; }
.stock-badge { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.stock-badge.a { background: rgba(45,106,79,0.08); color: #2d6a4f; }
.stock-badge.b { background: rgba(180,83,9,0.08); color: #b45309; }
.stock-badge.c { background: rgba(185,28,28,0.08); color: #b91c1c; }
.stock-score { text-align: center; margin-bottom: 16px; }
.stock-score-val { font-family: 'Space Grotesk', sans-serif; font-size: 42px; font-weight: 700; letter-spacing: -2px; line-height: 1; }
.stock-score-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; color: #a8a29e; margin-top: 4px; }
.stock-price-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #f0ece6; }
.stock-price-val { font-family: 'Space Grotesk', sans-serif; font-weight: 600; }
.stock-price-chg { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 500; }
.stock-price-chg.up { color: #2d6a4f; }
.stock-price-chg.down { color: #b91c1c; }
.stock-tech { margin-bottom: 14px; }
.stock-tech-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 12px; }
.stock-tech-item:not(:last-child) { border-bottom: 1px solid #f5f3ef; }
.stock-tech-name { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: #6b6560; }
.stock-tech-val { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.stock-summary { font-size: 12px; color: #6b6560; line-height: 1.6; padding-top: 12px; border-top: 1px solid #f0ece6; }
.sub-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 16px; margin-top: 40px; }
.sub-title { font-family: 'Space Grotesk', sans-serif; font-size: 14px; font-weight: 600; }
.hot-tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 1px 6px; border-radius: 3px; background: rgba(124,58,237,0.06); color: #7c3aed; margin-left: 4px; letter-spacing: 0.5px; }

/* Loading & Empty */
.loading-box { text-align: center; padding: 32px 0; color: #a8a29e; font-size: 14px; }
.empty-box { text-align: center; padding: 60px 0; }
.empty-box .empty-icon { font-size: 48px; margin-bottom: 16px; color: #d4cfc7; }
.empty-box p { color: #6b6560; font-size: 14px; margin-bottom: 16px; }

/* Links */
.head-subtitle { color: #6b6560; font-size: 13px; margin-bottom: 20px; }
.head-subtitle a { color: #c9774a; text-decoration: none; }
.head-subtitle a:hover { text-decoration: underline; }

/* Report meta bar */
.meta-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a8a29e; }
.meta-item { display: flex; align-items: center; gap: 4px; }

/* PDF export - print styles */
@media print {
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .no-print { display: none !important; }
  body { background: #fff; font-size: 12px; }
  .page-wrap { max-width: 100%; padding: 0; margin: 0; }
  .head { margin-bottom: 20px; padding-bottom: 12px; }
  .head h1 { font-size: 24px; }
  .sec-head { page-break-after: avoid; margin-bottom: 12px; margin-top: 24px; }
  .ai-box, .idx-card, .sector-tbl, .stock-card { page-break-inside: avoid; break-inside: avoid; }
  .idx-grid { gap: 8px; }
  .idx-card { padding: 12px; }
  .idx-price { font-size: 20px; }
  .stock-grid { gap: 8px; }
  .stock-card { padding: 12px; }
  .stock-score-val { font-size: 28px; }
  .sector-tbl { font-size: 11px; }
  .sector-tbl th, .sector-tbl td { padding: 6px 8px; }
}

@media (max-width: 900px) {
  .idx-grid, .stock-grid { grid-template-columns: 1fr 1fr; }
  .sector-tbl { font-size: 12px; }
}
@media (max-width: 600px) {
  .idx-grid, .stock-grid { grid-template-columns: 1fr; }
  .page-wrap { padding: 24px 16px; }
}
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
</head>
<body>
<div class="page-wrap" id="report-content">

  <div class="head">
    <div>
      <div class="head-label">Weekly Intelligence</div>
      <h1>投研<span>周报</span></h1>
      <div class="head-date" id="report-date">Loading...</div>
      <div class="meta-bar" id="meta-bar" style="display:none;">
        <span class="meta-item" id="meta-version"></span>
        <span class="meta-item" id="meta-model"></span>
        <span class="meta-item" id="meta-trigger"></span>
      </div>
    </div>
    <div class="head-right no-print">
      <select class="ver-select" id="ver-select" onchange="onVersionChange()">
        <option value="">选择版本...</option>
      </select>
      <button class="btn" onclick="exportPDF()">PDF</button>
    </div>
  </div>

  <!-- Section 1: Market Overview -->
  <div class="sec-head">
    <span class="sec-num">01</span>
    <h2 class="sec-title">大盘综述</h2>
    <span class="sec-sub">Market Overview</span>
  </div>
  <div id="section-market">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 2: Capital Flow -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">02</span>
    <h2 class="sec-title">资金面分析</h2>
    <span class="sec-sub">Capital Flow Analysis</span>
  </div>
  <div id="section-capital">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 3: Geopolitics -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">03</span>
    <h2 class="sec-title">国际局势</h2>
    <span class="sec-sub">Geopolitical Outlook</span>
  </div>
  <div id="section-geopolitics">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 4: Yield Curve -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">04</span>
    <h2 class="sec-title">国债收益率曲线</h2>
    <span class="sec-sub">Treasury Yield Curve</span>
  </div>
  <div id="section-yield-curve">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 5: Sector Analysis -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">05</span>
    <h2 class="sec-title">行业板块</h2>
    <span class="sec-sub">Sector Performance</span>
  </div>
  <div id="section-sector">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 6: Stock Scoring -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">06</span>
    <h2 class="sec-title">个股评分</h2>
    <span class="sec-sub">Stock Scoring</span>
    <span class="score-help" style="margin-left:8px;cursor:help;position:relative;display:inline-block;">
      <span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#c8b88a;color:#fff;font-size:12px;font-weight:700;">?</span>
      <span class="score-help-tip" style="display:none;position:absolute;left:24px;top:-10px;z-index:100;background:#1a1a1a;color:#e8e4d9;padding:14px 16px;border-radius:8px;font-size:12px;line-height:1.7;width:340px;box-shadow:0 4px 16px rgba(0,0,0,.3);font-weight:400;white-space:normal;">
        <b>评分规则 (1~5 分)</b><br>
        基准分 <b>3.0</b>，按四维指标加减分：<br>
        <b>A. 趋势 (40%)</b> EMA20/EMA50 多头排列 +1.0，斜率向上 +0.5，空头排列 -1.5<br>
        <b>B. MACD (30%)</b> 零轴上多头放量 +0.5，动能柱扩张 +0.5，空头主导 -1.0<br>
        <b>C. KDJ (20%)</b> J&gt;80 强势区 +0.5，J&lt;20 超跌区 -0.5<br>
        <b>D. 量价 (10%)</b> 放量上涨 (+50%量) +0.5<br>
        <span style="margin-top:6px;display:block;border-top:1px solid #333;padding-top:6px;">
        等级: AA ≥4.5 | A ≥4.0 | B ≥3.0 | C ≥2.0 | D &lt;2.0
        </span>
      </span>
    </span>
  </div>
  <div id="section-stocks">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 7: X Monitor -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">07</span>
    <h2 class="sec-title">X 舆情监控</h2>
    <span class="sec-sub">X Sentiment Monitor</span>
  </div>
  <div id="section-x-monitor">
    <div class="loading-box">加载中...</div>
  </div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script>
/* ─── Score help tooltip ─── */
document.addEventListener('DOMContentLoaded', function() {
  const helpEl = document.querySelector('.score-help');
  const tipEl = document.querySelector('.score-help-tip');
  if (helpEl && tipEl) {
    helpEl.addEventListener('mouseenter', function() { tipEl.style.display = 'block'; });
    helpEl.addEventListener('mouseleave', function() { tipEl.style.display = 'none'; });
  }
});

/* ─── Utilities ─── */
function chgClass(v) { return v >= 0 ? 'up' : 'down'; }
function chgStr(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function fmtPrice(v) { return v != null ? '$' + v.toFixed(2) : '-'; }
function badgeCls(r) { r = r.toLowerCase(); if (r === 'aa' || r === 'a') return 'a'; if (r === 'b') return 'b'; return 'c'; }

/* Markdown + LaTeX 渲染：先保护 $...$ / $$...$$ 不被 marked 吞掉下划线 */
function renderMd(text) {
  if (!text) return '';
  const mathBlocks = [];
  // 先保护 display math ($$...$$)
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (m) => {
    mathBlocks.push(m);
    return '%%MATH' + (mathBlocks.length - 1) + '%%';
  });
  // 再保护 inline math ($...$)
  text = text.replace(/\$([^\$]+?)\$/g, (m) => {
    mathBlocks.push(m);
    return '%%MATH' + (mathBlocks.length - 1) + '%%';
  });
  let html = marked.parse(text);
  // 恢复 LaTeX 公式
  html = html.replace(/%%MATH(\d+)%%/g, (_, i) => mathBlocks[i]);
  return html;
}

/* 对指定容器内的 .ai-text 执行 KaTeX 渲染 */
function renderLatex(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.querySelectorAll('.ai-text').forEach(node => {
    renderMathInElement(node, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false},
      ],
      throwOnError: false,
    });
  });
}

/* ─── Rendering ─── */
function renderMarket(data) {
  const idxHtml = (data.indices || []).map(idx =>
    `<div class="idx-card">
      <div class="idx-name">${idx.name}</div>
      <div class="idx-symbol">${idx.symbol}</div>
      <div class="idx-price">${idx.current.toLocaleString()}</div>
      <div class="idx-change ${chgClass(idx.weekly_change_pct)}">${chgStr(idx.weekly_change_pct)}</div>
      <div class="idx-change-label">本周涨跌幅（5日）</div>
    </div>`
  ).join('');

  document.getElementById('section-market').innerHTML =
    `<div class="idx-grid">${idxHtml}</div>` +
    `<div class="ai-box">
      <div class="ai-label">AI MARKET SUMMARY</div>
      <div class="ai-text">${renderMd(data.ai_market_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-market');
}

function renderCapital(data) {
  document.getElementById('section-capital').innerHTML =
    `<div class="ai-box">
      <div class="ai-label">AI CAPITAL FLOW ANALYSIS</div>
      <div class="ai-text">${renderMd(data.ai_capital_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-capital');
}

function renderGeopolitics(data) {
  document.getElementById('section-geopolitics').innerHTML =
    `<div class="ai-box">
      <div class="ai-label">AI GEOPOLITICAL OUTLOOK</div>
      <div class="ai-text">${renderMd(data.ai_geopolitics_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-geopolitics');
}

function renderYieldCurve(data) {
  const yc = data.yield_curve || {};
  const yields = yc.yields || {};
  const changes = yc.weekly_changes_bp || {};
  const spreads = yc.spreads || {};
  const spreadChanges = yc.spread_changes_bp || {};
  const cross = yc.cross_asset || {};
  const regime = yc.regime || 'Mixed';
  const regimeLogic = yc.regime_logic || '';

  const tenorOrder = ['3M', '2Y', '5Y', '10Y', '30Y'];
  const yieldsRows = tenorOrder.filter(t => yields[t] !== undefined).map(t => {
    const yld = yields[t];
    const chg = changes[t];
    let bpClass = 'flat', bpStr = '-';
    if (chg !== undefined && chg !== null) {
      bpClass = chg > 0 ? 'up' : chg < 0 ? 'down' : 'flat';
      bpStr = (chg >= 0 ? '+' : '') + chg.toFixed(1) + ' bp';
    }
    return `<tr><td class="yc-tenor">${t}</td><td class="yc-yield">${yld.toFixed(3)}%</td><td class="yc-bp ${bpClass}">${bpStr}</td></tr>`;
  }).join('');

  const spreadHtml = ['2s10s', '3m10s', '10s30s'].map(k => {
    const v = spreads[k], c = spreadChanges[k];
    if (v === undefined || v === null) return '';
    const cClass = c > 0 ? 'up' : c < 0 ? 'down' : 'flat';
    const cStr = c !== undefined && c !== null ? ((c >= 0 ? '+' : '') + c.toFixed(1) + ' bp') : '-';
    const valColor = v >= 0 ? '#2d6a4f' : '#b91c1c';
    return `<div class="yc-spread-item">
      <div class="yc-spread-name">${k.toUpperCase()}</div>
      <div class="yc-spread-val" style="color:${valColor}">${(v >= 0 ? '+' : '') + v.toFixed(1)} bp</div>
      <div class="yc-spread-chg yc-bp ${cClass}">本周 ${cStr}</div>
    </div>`;
  }).join('');

  const crossOrder = ['VIX', 'DXY', 'GLD', 'CL=F', 'SPY'];
  const crossHtml = crossOrder.filter(k => cross[k]).map(k => {
    const c = cross[k];
    const chgPct = c.weekly_change_pct;
    const chgClass2 = chgPct > 0 ? 'up' : chgPct < 0 ? 'down' : 'flat';
    return `<div class="yc-cross-item">
      <div class="yc-cross-name">${k}</div>
      <div class="yc-cross-val">${c.current}</div>
      <div class="yc-cross-chg yc-bp ${chgClass2}">${(chgPct >= 0 ? '+' : '') + chgPct.toFixed(2)}%</div>
    </div>`;
  }).join('');

  const regimeClass = regime.toLowerCase().replace(/\s+/g, '-');

  document.getElementById('section-yield-curve').innerHTML =
    `<div class="yc-grid">
      <div class="yc-card">
        <div class="yc-regime">
          <span class="yc-regime-badge ${regimeClass}">${regime}</span>
          <span class="yc-regime-logic">${regimeLogic}</span>
        </div>
        <div class="yc-spreads">${spreadHtml}</div>
      </div>
      <div class="yc-card">
        <table class="yc-yields-tbl">
          <thead><tr><th>期限</th><th>收益率</th><th>本周变化</th></tr></thead>
          <tbody>${yieldsRows}</tbody>
        </table>
      </div>
    </div>` +
    `<div class="yc-card" style="margin-bottom:16px">
      <div class="ai-label" style="margin-bottom:8px">CROSS-ASSET</div>
      <div class="yc-cross">${crossHtml}</div>
    </div>` +
    `<div class="ai-box">
      <div class="ai-label">AI YIELD CURVE ANALYSIS</div>
      <div class="ai-text">${renderMd(data.ai_yield_curve_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-yield-curve');
}

function renderSector(data) {
  const rows = (data.sectors || []).map(s =>
    `<tr>
      <td><span class="sector-name">${s.name}</span><span class="sector-etf">${s.symbol}</span></td>
      <td class="chg ${chgClass(s.weekly_change_pct)}">${chgStr(s.weekly_change_pct)}</td>
      <td class="chg ${chgClass(s.chg_15d)}">${chgStr(s.chg_15d)}</td>
      <td class="chg ${chgClass(s.chg_30d)}">${chgStr(s.chg_30d)}</td>
      <td>${fmtPrice(s.current)}</td>
      <td>${s.vol_ratio}</td>
    </tr>`
  ).join('');

  document.getElementById('section-sector').innerHTML =
    `<table class="sector-tbl"><thead><tr>
      <th>行业</th><th>5日</th><th>15日</th><th>30日</th><th>当前价</th><th>量比</th>
    </tr></thead><tbody>${rows}</tbody></table>` +
    `<div class="ai-box" style="margin-top:20px">
      <div class="ai-label">AI SECTOR ANALYSIS</div>
      <div class="ai-text">${renderMd(data.ai_sector_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-sector');
}

function renderStocks(data) {
  function cardHtml(stocks) {
    return (stocks || []).map(s => {
      let techHtml = '';
      if (s.tech) {
        techHtml = Object.entries(s.tech).map(([k, v]) =>
          `<div class="stock-tech-item"><span class="stock-tech-name">${k}</span><span class="stock-tech-val">${v}</span></div>`
        ).join('');
      }
      return `<div class="stock-card">
        <div class="stock-card-head"><span class="stock-sym">${s.symbol}</span><span class="stock-badge ${badgeCls(s.rating)}">${s.rating}</span></div>
        <div class="stock-score"><div class="stock-score-val">${s.score}/5</div><div class="stock-score-label">综合评分</div></div>
        <div class="stock-price-row">
          <span>当前价 <span class="stock-price-val">${fmtPrice(s.price)}</span></span>
          <span class="stock-price-chg ${chgClass(s.change_pct)}">${chgStr(s.change_pct)}</span>
        </div>
        <div class="stock-tech">${techHtml}</div>
        <div class="stock-summary">${s.summary || ''}</div>
      </div>`;
    }).join('');
  }

  document.getElementById('section-stocks').innerHTML =
    `<div class="sub-head"><span class="sub-title">关注列表</span></div>` +
    `<div class="stock-grid">${cardHtml(data.watchlist_scores)}</div>` +
    `<div class="sub-head"><span class="sub-title">本周热门股 <span class="hot-tag">AUTO</span></span></div>` +
    `<div class="stock-grid">${cardHtml(data.hot_stock_scores)}</div>`;
}

function renderXMonitor(data) {
  const x = data.x_tweets_data || {};
  const total = x.total_count || 0;
  const sd = x.sentiment_distribution || {bullish: 0, bearish: 0, neutral: 0};
  const accounts = x.accounts || [];
  const topAssets = x.top_assets_mentioned || [];
  const topTweets = x.top_tweets || [];
  const days = x.window_days || 7;

  if (!total) {
    document.getElementById('section-x-monitor').innerHTML =
      `<div class="xm-empty">本周暂无 X 关键账号推文数据</div>` +
      `<div class="ai-box" style="margin-top:16px">
        <div class="ai-label">AI X SENTIMENT MONITOR</div>
        <div class="ai-text">${renderMd(data.ai_x_monitor_summary || 'AI 分析暂不可用')}</div>
      </div>`;
    renderLatex('section-x-monitor');
    return;
  }

  const overviewHtml = `<div class="xm-card">
    <div class="xm-card-title">舆情分布 · 近 ${days} 天 · ${total} 条推文 · ${accounts.length} 个账号</div>
    <div class="xm-stats">
      <div class="xm-stat"><div class="xm-stat-val xm-sentiment-bullish">${sd.bullish || 0}</div><div class="xm-stat-label">BULLISH</div></div>
      <div class="xm-stat"><div class="xm-stat-val xm-sentiment-neutral">${sd.neutral || 0}</div><div class="xm-stat-label">NEUTRAL</div></div>
      <div class="xm-stat"><div class="xm-stat-val xm-sentiment-bearish">${sd.bearish || 0}</div><div class="xm-stat-label">BEARISH</div></div>
    </div>
  </div>`;

  const assetsHtml = `<div class="xm-card">
    <div class="xm-card-title">热议标的 TOP ${Math.min(topAssets.length, 15)}</div>
    <div class="xm-asset-list">
      ${topAssets.length === 0 ? '<span style="color:#a8a29e;font-size:12px;">暂无</span>' :
        topAssets.map(a => `<span class="xm-asset-tag">${a.ticker}<b>${a.count}</b></span>`).join('')}
    </div>
  </div>`;

  const tweetsHtml = topTweets.map(t => {
    const sent = t.sentiment || 'neutral';
    const dt = t.created_at ? t.created_at.slice(0, 10) : '';
    const assetTags = (t.impact_assets || []).map(a => `<span class="xm-asset-tag">${a}</span>`).join('');
    const impact = t.market_impact ? `<div class="xm-tweet-impact"><b>市场影响：</b>${escapeHtml(t.market_impact)}</div>` : '';
    return `<div class="xm-tweet-card">
      <div class="xm-tweet-head">
        <span class="xm-tweet-user">${escapeHtml(t.username || '')}</span>
        <span class="xm-tweet-meta">
          <span class="xm-sentiment-pill ${sent}">${sent}</span>
          <span>${dt}</span>
          <span>&hearts; ${t.like_count || 0}</span>
          <span>&#8634; ${t.retweet_count || 0}</span>
        </span>
      </div>
      ${t.text_zh ? `<div class="xm-tweet-zh">${escapeHtml(t.text_zh)}</div>` : ''}
      ${t.text ? `<div class="xm-tweet-text">${escapeHtml(t.text)}</div>` : ''}
      ${impact}
      ${assetTags ? `<div class="xm-tweet-assets">${assetTags}</div>` : ''}
    </div>`;
  }).join('');

  document.getElementById('section-x-monitor').innerHTML =
    `<div class="xm-grid">${overviewHtml}${assetsHtml}</div>` +
    (tweetsHtml ? `<div class="xm-card" style="margin-bottom:16px">
      <div class="xm-card-title">本周代表性推文</div>
      <div class="xm-tweet-list">${tweetsHtml}</div>
    </div>` : '') +
    `<div class="ai-box">
      <div class="ai-label">AI X SENTIMENT MONITOR</div>
      <div class="ai-text">${renderMd(data.ai_x_monitor_summary || 'AI 分析暂不可用')}</div>
    </div>`;
  renderLatex('section-x-monitor');
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function showEmpty() {
  const html = `<div class="empty-box">
    <div class="empty-icon">&#x1f4ca;</div>
    <p>暂无已生成的周报，请联系管理员生成</p>
  </div>`;
  ['section-market', 'section-capital', 'section-geopolitics', 'section-yield-curve', 'section-sector', 'section-stocks', 'section-x-monitor'].forEach(id => {
    document.getElementById(id).innerHTML = '';
  });
  document.querySelector('.page-wrap').insertAdjacentHTML('beforeend', html);
}

/* ─── Data Loading ─── */
async function loadVersions() {
  try {
    const resp = await fetch('/api/report/versions');
    const versions = await resp.json();
    const sel = document.getElementById('ver-select');
    sel.innerHTML = '<option value="">选择版本...</option>';
    versions.forEach(v => {
      const date = v.report_date ? v.report_date.slice(0, 10) : '';
      const opt = document.createElement('option');
      opt.value = v.id;
      opt.textContent = `v${v.version} - ${date} (${v.model_name || ''}, ${v.trigger === 'scheduled' ? '定时' : '手动'})`;
      sel.appendChild(opt);
    });
    return versions;
  } catch (e) {
    console.error('loadVersions error:', e);
    return [];
  }
}

async function loadReport(reportId) {
  try {
    const resp = await fetch(`/api/report/${reportId}`);
    const data = await resp.json();
    if (data.error) {
      ['section-market', 'section-capital', 'section-geopolitics', 'section-yield-curve', 'section-sector', 'section-stocks', 'section-x-monitor'].forEach(id => {
        document.getElementById(id).innerHTML = `<div class="loading-box">${data.error}</div>`;
      });
      return;
    }
    // Update meta
    const date = data.report_date ? data.report_date.slice(0, 10) : '';
    document.getElementById('report-date').textContent = date;
    const metaBar = document.getElementById('meta-bar');
    metaBar.style.display = 'flex';
    document.getElementById('meta-version').textContent = 'v' + data.version;
    document.getElementById('meta-model').textContent = data.model_name || '';
    document.getElementById('meta-trigger').textContent = data.trigger === 'scheduled' ? '定时生成' : '手动生成';

    renderMarket(data.market);
    renderCapital(data.capital);
    renderGeopolitics(data.geopolitics);
    renderYieldCurve(data.yield_curve || {});
    renderSector(data.sector);
    renderStocks(data.stocks);
    renderXMonitor(data.x_monitor || {});
  } catch (e) {
    console.error('loadReport error:', e);
    ['section-market', 'section-capital', 'section-geopolitics', 'section-yield-curve', 'section-sector', 'section-stocks', 'section-x-monitor'].forEach(id => {
      document.getElementById(id).innerHTML = '<div class="loading-box">加载失败</div>';
    });
  }
}

function onVersionChange() {
  const sel = document.getElementById('ver-select');
  const id = sel.value;
  if (id) {
    // Remove any empty-box
    const empty = document.querySelector('.empty-box');
    if (empty) empty.remove();
    ['section-market', 'section-capital', 'section-geopolitics', 'section-yield-curve', 'section-sector', 'section-stocks', 'section-x-monitor'].forEach(s => {
      document.getElementById(s).innerHTML = '<div class="loading-box">加载中...</div>';
    });
    loadReport(id);
  }
}

/* ─── PDF Export ─── */
function exportPDF() {
  const src = document.getElementById('report-content');
  const ver = document.getElementById('meta-version').textContent || 'report';

  // 克隆 DOM，在克隆上修改布局不影响原页面
  const clone = src.cloneNode(true);
  clone.removeAttribute('id');

  // 移除不需要打印的元素
  clone.querySelectorAll('.no-print').forEach(el => el.remove());

  // A4 纵向：210mm - 2*8mm margin = 194mm ≈ 734px @96dpi
  // 必须覆盖 page-wrap 的原始 padding/max-width
  const PDF_WIDTH = 734;
  const GAP = 10;
  const CARD_W = Math.floor((PDF_WIDTH - GAP * 2) / 3);  // (734-20)/3 ≈ 238

  clone.style.width = PDF_WIDTH + 'px';
  clone.style.maxWidth = PDF_WIDTH + 'px';
  clone.style.padding = '0';
  clone.style.margin = '0';
  clone.style.boxSizing = 'content-box';
  clone.style.background = '#fff';

  // 覆盖 page-wrap 内部可能的 padding
  clone.querySelectorAll('.page-wrap').forEach(el => {
    el.style.padding = '0';
    el.style.maxWidth = '100%';
    el.style.margin = '0';
  });

  // 强制所有子元素 box-sizing: border-box
  clone.querySelectorAll('*').forEach(el => {
    el.style.boxSizing = 'border-box';
  });

  // Grid → 按行分组，每行 3 个卡片放在一个不跨页的容器内
  clone.querySelectorAll('.idx-grid, .stock-grid').forEach(grid => {
    const cards = Array.from(grid.children);
    grid.innerHTML = '';
    grid.style.display = 'block';
    grid.style.padding = '0';
    grid.style.margin = '0';

    for (let i = 0; i < cards.length; i += 3) {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.flexWrap = 'nowrap';
      row.style.gap = GAP + 'px';
      row.style.marginBottom = GAP + 'px';
      row.style.pageBreakInside = 'avoid';
      row.style.breakInside = 'avoid';

      for (let j = 0; j < 3 && i + j < cards.length; j++) {
        const card = cards[i + j];
        card.style.width = CARD_W + 'px';
        card.style.flex = '0 0 ' + CARD_W + 'px';
        card.style.boxSizing = 'border-box';
        row.appendChild(card);
      }
      grid.appendChild(row);
    }
  });

  // AI 摘要框、行业表格也不跨页
  clone.querySelectorAll('.ai-box, .sector-tbl, .sec-head').forEach(el => {
    el.style.pageBreakInside = 'avoid';
    el.style.breakInside = 'avoid';
  });

  // 行业表格也缩窄
  clone.querySelectorAll('.sector-tbl').forEach(tbl => {
    tbl.style.width = PDF_WIDTH + 'px';
    tbl.style.fontSize = '11px';
  });

  // 临时插入 body（opacity:0 但在文档流中，html2canvas 可渲染）
  const wrapper = document.createElement('div');
  wrapper.style.cssText = 'position:fixed;top:0;left:0;width:' + PDF_WIDTH + 'px;z-index:-1;opacity:0;pointer-events:none;background:#fff;';
  wrapper.appendChild(clone);
  document.body.appendChild(wrapper);

  const opt = {
    margin: [8, 8, 8, 8],
    filename: `weekly-report-${ver}.pdf`,
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: { scale: 2, useCORS: true },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    pagebreak: { mode: ['avoid-all', 'css', 'legacy'] },
  };

  html2pdf().set(opt).from(clone).save().then(() => {
    document.body.removeChild(wrapper);
  }).catch(() => {
    document.body.removeChild(wrapper);
  });
}

/* ─── Init ─── */
(async function() {
  const versions = await loadVersions();

  // Check URL param for version
  const urlParams = new URLSearchParams(window.location.search);
  const verParam = urlParams.get('v');

  if (verParam) {
    // Find report by version number
    const match = versions.find(v => v.version === parseInt(verParam));
    if (match) {
      document.getElementById('ver-select').value = match.id;
      await loadReport(match.id);
      return;
    }
  }

  // Default: load latest
  if (versions.length > 0) {
    document.getElementById('ver-select').value = versions[0].id;
    await loadReport(versions[0].id);
  } else {
    showEmpty();
  }
})();
</script>
</body>
</html>"""
