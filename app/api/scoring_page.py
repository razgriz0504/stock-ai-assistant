"""投研周报页面 - 路由 + 内联 HTML（大盘综述 + 行业板块 + 个股评分）"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.models import SessionLocal, UserPreference
from app.report.weekly_report import (
    get_report_section_market,
    get_report_section_sector,
    get_report_section_stocks,
)

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_USER_ID = "web_default"


class RefreshRequest(BaseModel):
    force: bool = False


@router.get("/scoring", response_class=HTMLResponse)
async def scoring_page():
    return _build_html()


@router.get("/api/report/section/{section}")
async def get_report_section(section: str):
    """按 section 加载周报数据"""
    if section == "market":
        return await get_report_section_market()
    elif section == "sector":
        return await get_report_section_sector()
    elif section == "stocks":
        db = SessionLocal()
        try:
            pref = db.query(UserPreference).filter(
                UserPreference.feishu_user_id == WEB_USER_ID
            ).first()
            watchlist = json.loads(pref.watchlist) if pref and pref.watchlist else []
            return await get_report_section_stocks(watchlist)
        finally:
            db.close()
    return {"error": "Unknown section"}


@router.post("/api/report/refresh")
async def refresh_report(req: RefreshRequest = RefreshRequest(force=False)):
    """强制刷新整个周报"""
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        watchlist = json.loads(pref.watchlist) if pref and pref.watchlist else []
    finally:
        db.close()

    market, sector, stocks = await asyncio.gather(
        get_report_section_market(),
        get_report_section_sector(),
        get_report_section_stocks(watchlist),
    )
    return {
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": {"market": market, "sector": sector, "stocks": stocks},
    }


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

/* Header */
.page-wrap { max-width: 1100px; margin: 0 auto; padding: 40px 32px; }
.head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid #e8e4de; }
.head-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; color: #c9774a; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.head-label::before { content: ''; display: inline-block; width: 6px; height: 6px; background: #c9774a; border-radius: 50%; }
.head h1 { font-family: 'Space Grotesk', sans-serif; font-size: 32px; font-weight: 700; margin: 0; }
.head h1 span { color: #c9774a; }
.head-date { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #6b6560; margin-top: 8px; }
.head-right { display: flex; align-items: center; gap: 12px; }
.btn-refresh { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px 16px; border-radius: 6px; border: 1px solid #d4cfc7; background: #fff; color: #1a1a1a; cursor: pointer; }
.btn-refresh:hover { border-color: #c9774a; color: #c9774a; }

/* Section headers */
.sec-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 24px; }
.sec-num { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #c9774a; letter-spacing: 1px; }
.sec-title { font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: 600; }
.sec-sub { font-size: 13px; color: #6b6560; margin-left: auto; }

/* Index Cards */
.idx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.idx-card { background: #fff; padding: 24px; border: 1px solid #e8e4de; border-radius: 10px; position: relative; }
.idx-card:hover { border-color: #c9774a; }
.idx-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; color: #6b6560; margin-bottom: 4px; }
.idx-symbol { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a8a29e; margin-bottom: 16px; }
.idx-price { font-family: 'Space Grotesk', sans-serif; font-size: 28px; font-weight: 700; letter-spacing: -1px; margin-bottom: 8px; }
.idx-change { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500; }
.idx-change.up { color: #2d6a4f; }
.idx-change.down { color: #b91c1c; }
.idx-spark { margin-top: 20px; height: 48px; }
.idx-spark canvas { width: 100%; height: 100%; display: block; }

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

/* Loading */
.loading-box { text-align: center; padding: 32px 0; color: #a8a29e; font-size: 14px; }

/* Links */
.head-subtitle { color: #6b6560; font-size: 13px; margin-bottom: 20px; }
.head-subtitle a { color: #c9774a; text-decoration: none; }
.head-subtitle a:hover { text-decoration: underline; }

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
<div class="page-wrap">

  <div class="head">
    <div>
      <div class="head-label">Weekly Intelligence</div>
      <h1>投研<span>周报</span></h1>
      <div class="head-date" id="report-date">Loading...</div>
    </div>
    <div class="head-right">
      <button class="btn-refresh" onclick="refreshAll()">&#x21bb; 刷新</button>
    </div>
  </div>
  <p class="head-subtitle"><a href="/watchlist">管理关注列表</a></p>

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

<script>
function chgClass(v) { return v >= 0 ? 'up' : 'down'; }
function chgStr(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
function fmtPrice(v) { return v != null ? '$' + v.toFixed(2) : '-'; }
function badgeCls(r) { r = r.toLowerCase(); if (r === 'aa' || r === 'a') return 'a'; if (r === 'b') return 'b'; return 'c'; }
function momentumCls(m) { if (m === '强势') return 'strong'; if (m === '偏强') return 'mid'; if (m === '偏弱') return 'weak'; return 'mid'; }

function renderMarket(data) {
  const idxHtml = data.indices.map(idx =>
    `<div class="idx-card">
      <div class="idx-label">${idx.name}</div>
      <div class="idx-symbol">${idx.symbol}</div>
      <div class="idx-price">${idx.current.toLocaleString()}</div>
      <div class="idx-change ${chgClass(idx.weekly_change_pct)}">${chgStr(idx.weekly_change_pct)}</div>
      <div class="idx-spark"><canvas id="spark-${idx.symbol}"></canvas></div>
    </div>`
  ).join('');

  document.getElementById('section-market').innerHTML =
    `<div class="idx-grid">${idxHtml}</div>` +
    `<div class="ai-box">
      <div class="ai-label">AI MARKET SUMMARY</div>
      <div class="ai-text">${data.ai_market_summary || 'AI 分析暂不可用'}</div>
    </div>`;

  // Draw sparklines
  data.indices.forEach(idx => {
    const canvas = document.getElementById('spark-' + idx.symbol);
    if (!canvas) return;
    const color = idx.weekly_change_pct >= 0 ? '#2d6a4f' : '#b91c1c';
    sparkline(canvas, idx.sparkline, color);
  });
}

function renderSector(data) {
  const rows = data.sectors.map(s =>
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
  function cardHtml(stocks, showMomentum) {
    return stocks.map(s => {
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
    `<div class="stock-grid">${cardHtml(data.watchlist_scores, false)}</div>` +
    `<div class="sub-head"><span class="sub-title">本周热门股 <span class="hot-tag">AUTO</span></span></div>` +
    `<div class="stock-grid">${cardHtml(data.hot_stock_scores, true)}</div>`;
}

function sparkline(canvas, data, color) {
  const ctx = canvas.getContext('2d');
  const parent = canvas.parentElement;
  const w = parent.clientWidth || 280;
  const h = 48;
  canvas.width = w * 2; canvas.height = h * 2;
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  ctx.scale(2, 2);
  const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1;
  const step = w / (data.length - 1);
  ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  data.forEach((v, i) => { const px = i * step, py = h - 6 - ((v - mn) / rng) * (h - 12); i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py); });
  ctx.stroke();
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
  ctx.fillStyle = color.replace(')', ',0.06)').replace('rgb', 'rgba');
  ctx.fill();
  const lastX = (data.length - 1) * step;
  const lastY = h - 6 - ((data[data.length - 1] - mn) / rng) * (h - 12);
  ctx.beginPath(); ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
}

async function loadSection(section) {
  try {
    const resp = await fetch('/api/report/section/' + section);
    const data = await resp.json();
    if (section === 'market') renderMarket(data);
    else if (section === 'sector') renderSector(data);
    else if (section === 'stocks') renderStocks(data);
  } catch (e) {
    document.getElementById('section-' + section).innerHTML =
      '<div class="loading-box">加载失败: ' + e.message + '</div>';
  }
}

async function refreshAll() {
  ['market', 'sector', 'stocks'].forEach(s => {
    document.getElementById('section-' + s).innerHTML = '<div class="loading-box">加载中...</div>';
  });
  await loadSection('market');
  await loadSection('sector');
  await loadSection('stocks');
}

// Init
(async function() {
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  document.getElementById('report-date').textContent =
    weekStart.toISOString().slice(0, 10) + ' — ' + now.toISOString().slice(0, 10) + ' · Week ' + Math.ceil(now.getDate() / 7);
  await loadSection('market');
  await loadSection('sector');
  await loadSection('stocks');
})();
</script>
</body>
</html>"""