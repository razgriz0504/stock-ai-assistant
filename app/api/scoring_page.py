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

  <!-- Section 2: Sector Analysis -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">02</span>
    <h2 class="sec-title">行业板块</h2>
    <span class="sec-sub">Sector Performance</span>
  </div>
  <div id="section-sector">
    <div class="loading-box">加载中...</div>
  </div>

  <!-- Section 3: Stock Scoring -->
  <div class="sec-head" style="margin-top:48px">
    <span class="sec-num">03</span>
    <h2 class="sec-title">个股评分</h2>
    <span class="sec-sub">Stock Scoring</span>
  </div>
  <div id="section-stocks">
    <div class="loading-box">加载中...</div>
  </div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
<script>
/* ─── Utilities ─── */
function chgClass(v) { return v >= 0 ? 'up' : 'down'; }
function chgStr(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function fmtPrice(v) { return v != null ? '$' + v.toFixed(2) : '-'; }
function badgeCls(r) { r = r.toLowerCase(); if (r === 'aa' || r === 'a') return 'a'; if (r === 'b') return 'b'; return 'c'; }

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
      <div class="ai-text">${data.ai_market_summary || 'AI 分析暂不可用'}</div>
    </div>`;
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
      <div class="ai-text">${data.ai_sector_summary || 'AI 分析暂不可用'}</div>
    </div>`;
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
        <div class="stock-score"><div class="stock-score-val">${s.score}</div><div class="stock-score-label">综合评分</div></div>
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

function showEmpty() {
  const html = `<div class="empty-box">
    <div class="empty-icon">&#x1f4ca;</div>
    <p>暂无已生成的周报，请联系管理员生成</p>
  </div>`;
  ['section-market', 'section-sector', 'section-stocks'].forEach(id => {
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
      ['section-market', 'section-sector', 'section-stocks'].forEach(id => {
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
    renderSector(data.sector);
    renderStocks(data.stocks);
  } catch (e) {
    console.error('loadReport error:', e);
    ['section-market', 'section-sector', 'section-stocks'].forEach(id => {
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
    ['section-market', 'section-sector', 'section-stocks'].forEach(s => {
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

  // A4 纵向：210mm - 16mm 边距 = 194mm ≈ 734px @96dpi
  // PDF margin 已提供边距，克隆不加 padding 避免挤占内容区
  const PDF_WIDTH = 734;
  const CARD_W = 236;  // (734 - 2*13) / 3 ≈ 236
  const GAP = 13;

  clone.style.width = PDF_WIDTH + 'px';
  clone.style.maxWidth = PDF_WIDTH + 'px';
  clone.style.padding = '0';
  clone.style.boxSizing = 'content-box';
  clone.style.background = '#fff';

  // 强制所有子元素 box-sizing: border-box，确保卡片宽度含 padding/border
  clone.querySelectorAll('*').forEach(el => {
    el.style.boxSizing = 'border-box';
  });

  // Grid → flexbox，卡片固定宽度适配 3 列
  clone.querySelectorAll('.idx-grid, .stock-grid').forEach(grid => {
    grid.style.display = 'flex';
    grid.style.flexWrap = 'wrap';
    grid.style.gap = GAP + 'px';
    Array.from(grid.children).forEach(card => {
      card.style.width = CARD_W + 'px';
      card.style.flex = '0 0 ' + CARD_W + 'px';
      card.style.boxSizing = 'border-box';
    });
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
