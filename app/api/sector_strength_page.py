"""板块强度雷达 - 独立实时页面"""

import asyncio
import logging
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.data.sector_strength import fetch_enhanced_sector_data

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/sector-strength/data")
async def get_sector_strength_data(force_refresh: bool = Query(False)):
    """返回增强板块数据 JSON"""
    try:
        data = await asyncio.to_thread(fetch_enhanced_sector_data, use_cache=not force_refresh)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Sector strength data error: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.get("/sector-strength", response_class=HTMLResponse)
async def sector_strength_page():
    """板块强度雷达页面"""
    return _PAGE_HTML


_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>板块强度雷达 - Stock AI Assistant</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; padding: 24px; }
.container { max-width: 1200px; margin: 0 auto; }

/* Header */
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.header h1 { font-size: 24px; color: #4fc3f7; }
.header-right { display: flex; align-items: center; gap: 16px; }
.header-right .ts { font-size: 12px; color: #78909c; }
.btn { padding: 8px 16px; border: 1px solid #4fc3f7; background: transparent; color: #4fc3f7; border-radius: 6px; cursor: pointer; font-size: 13px; transition: background .2s; }
.btn:hover { background: #4fc3f722; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-home { border-color: #78909c; color: #78909c; }
.btn-home:hover { background: #78909c22; }

/* Summary Cards */
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.card { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 10px; padding: 16px; }
.card-label { font-size: 11px; color: #78909c; text-transform: uppercase; margin-bottom: 4px; }
.card-value { font-size: 20px; font-weight: 700; color: #e0e0e0; }
.card-value .sym { color: #4fc3f7; font-size: 14px; margin-left: 6px; }

/* Filters */
.filters { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-btn { padding: 6px 14px; border: 1px solid #2a3a4a; background: transparent; color: #b0bec5; border-radius: 16px; cursor: pointer; font-size: 12px; transition: all .2s; }
.filter-btn.active { border-color: #4fc3f7; color: #4fc3f7; background: #4fc3f711; }
.sort-label { margin-left: auto; font-size: 12px; color: #78909c; }
.sort-select { background: #1a2634; border: 1px solid #2a3a4a; color: #e0e0e0; padding: 4px 8px; border-radius: 4px; font-size: 12px; }

/* Table */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th { text-align: left; padding: 10px 8px; color: #78909c; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #2a3a4a; white-space: nowrap; cursor: pointer; }
thead th:hover { color: #4fc3f7; }
tbody tr { border-bottom: 1px solid #1a2634; transition: background .15s; }
tbody tr:hover { background: #1a263488; }
tbody td { padding: 10px 8px; white-space: nowrap; }
.sym-cell { display: flex; align-items: center; gap: 8px; }
.sym-ticker { font-weight: 700; color: #e0e0e0; font-family: 'JetBrains Mono', monospace; }
.sym-name { color: #78909c; font-size: 12px; }
.cat-badge { font-size: 10px; padding: 2px 6px; border-radius: 8px; }
.cat-spdr { background: #4fc3f722; color: #4fc3f7; }
.cat-thematic { background: #ab47bc22; color: #ce93d8; }
.up { color: #66bb6a; }
.down { color: #ef5350; }
.flow-in { color: #66bb6a; font-weight: 600; }
.flow-out { color: #ef5350; font-weight: 600; }
.flow-neutral { color: #78909c; }
.rank-num { color: #78909c; font-size: 12px; width: 28px; text-align: center; }

/* Flow Panel */
.flow-panel { margin-top: 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.flow-section { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 10px; padding: 16px; }
.flow-section h3 { font-size: 13px; color: #78909c; margin-bottom: 10px; }
.flow-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.flow-tag { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.flow-tag.inflow { background: #66bb6a22; color: #66bb6a; }
.flow-tag.outflow { background: #ef535022; color: #ef5350; }

/* Benchmark bar */
.benchmark { background: #1a2634; border: 1px solid #2a3a4a; border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; display: flex; align-items: center; gap: 16px; font-size: 13px; }
.benchmark .label { color: #78909c; }
.benchmark .val { font-weight: 600; }

/* Loading */
.loading { text-align: center; padding: 60px; color: #78909c; }
.loading .spin { display: inline-block; width: 24px; height: 24px; border: 3px solid #2a3a4a; border-top-color: #4fc3f7; border-radius: 50%; animation: spin .8s linear infinite; margin-bottom: 12px; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .cards { grid-template-columns: 1fr; }
  .flow-panel { grid-template-columns: 1fr; }
  body { padding: 12px; }
}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>板块强度雷达</h1>
    <div class="header-right">
      <span class="ts" id="updated-at"></span>
      <button class="btn" id="btn-refresh" onclick="loadData(true)">刷新</button>
      <a href="/" class="btn btn-home">首页</a>
    </div>
  </div>

  <div id="content">
    <div class="loading"><div class="spin"></div><div>加载数据中...</div></div>
  </div>
</div>

<script>
let DATA = null;
let currentFilter = 'all';
let currentSort = 'composite';

async function loadData(force = false) {
  const btn = document.getElementById('btn-refresh');
  btn.disabled = true;
  btn.textContent = '加载中...';
  try {
    const url = '/api/sector-strength/data' + (force ? '?force_refresh=true' : '');
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('请求失败');
    DATA = await resp.json();
    render();
  } catch (e) {
    document.getElementById('content').innerHTML =
      `<div class="loading" style="color:#ef5350">加载失败: ${e.message}<br><br><button class="btn" onclick="loadData(true)">重试</button></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '刷新';
  }
}

function chg(v) {
  if (v === null || v === undefined) return '<span style="color:#78909c">N/A</span>';
  const cls = v >= 0 ? 'up' : 'down';
  return `<span class="${cls}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
}

function rsVal(v) {
  if (v === null || v === undefined) return '<span style="color:#78909c">N/A</span>';
  const cls = v >= 0 ? 'up' : 'down';
  return `<span class="${cls}">${v >= 0 ? '+' : ''}${v.toFixed(2)}</span>`;
}

function flowBadge(flow) {
  if (!flow) return '<span class="flow-neutral">-</span>';
  const dir = flow.direction || 'neutral';
  if (dir === 'inflow') return `<span class="flow-in">▲ 流入</span>`;
  if (dir === 'outflow') return `<span class="flow-out">▼ 流出</span>`;
  return `<span class="flow-neutral">— 中性</span>`;
}

function getFiltered() {
  if (!DATA || !DATA.sectors) return [];
  let list = DATA.sectors;
  if (currentFilter === 'spdr') list = list.filter(s => s.category === 'spdr');
  if (currentFilter === 'thematic') list = list.filter(s => s.category === 'thematic');
  return sortList(list);
}

function sortList(list) {
  const clone = [...list];
  const key = currentSort;
  clone.sort((a, b) => {
    let va, vb;
    if (key === 'composite') { va = a.rs?.composite; vb = b.rs?.composite; }
    else if (key === 'chg_5d') { va = a.chg_5d; vb = b.chg_5d; }
    else if (key === 'chg_15d') { va = a.chg_15d; vb = b.chg_15d; }
    else if (key === 'chg_30d') { va = a.chg_30d; vb = b.chg_30d; }
    else if (key === 'chg_60d') { va = a.chg_60d; vb = b.chg_60d; }
    else if (key === 'flow') { va = a.flow?.accumulation; vb = b.flow?.accumulation; }
    else if (key === 'vol_ratio') { va = a.vol_ratio; vb = b.vol_ratio; }
    else { va = a.rs?.composite; vb = b.rs?.composite; }
    va = va ?? -999; vb = vb ?? -999;
    return vb - va;
  });
  return clone;
}

function render() {
  if (!DATA) return;
  const stats = DATA.summary_stats || {};
  const bm = DATA.benchmark || {};
  const sectors = getFiltered();

  // 找出资金流入/流出的 ETF
  const inflowETFs = DATA.sectors.filter(s => s.flow?.direction === 'inflow');
  const outflowETFs = DATA.sectors.filter(s => s.flow?.direction === 'outflow');

  let html = '';

  // Summary cards
  html += `<div class="cards">
    <div class="card"><div class="card-label">最强板块 (RS)</div><div class="card-value">${stats.strongest_theme || '-'}<span class="sym">${stats.strongest_symbol || ''}</span></div></div>
    <div class="card"><div class="card-label">跑赢 SPY (30日)</div><div class="card-value">${stats.sectors_above_spy_30d ?? 0} / ${stats.total_etfs ?? 0}</div></div>
    <div class="card"><div class="card-label">资金流入信号</div><div class="card-value">${inflowETFs.length} 个板块</div></div>
  </div>`;

  // Benchmark
  html += `<div class="benchmark">
    <span class="label">基准 SPY:</span>
    <span class="val">$${bm.current || '-'}</span>
    <span>5日 ${chg(bm.chg_5d)}</span>
    <span>15日 ${chg(bm.chg_15d)}</span>
    <span>30日 ${chg(bm.chg_30d)}</span>
  </div>`;

  // Filters
  html += `<div class="filters">
    <button class="filter-btn ${currentFilter==='all'?'active':''}" onclick="setFilter('all')">全部 (${DATA.sectors.length})</button>
    <button class="filter-btn ${currentFilter==='spdr'?'active':''}" onclick="setFilter('spdr')">SPDR 行业</button>
    <button class="filter-btn ${currentFilter==='thematic'?'active':''}" onclick="setFilter('thematic')">主题 ETF</button>
    <span class="sort-label">排序:</span>
    <select class="sort-select" onchange="setSort(this.value)">
      <option value="composite" ${currentSort==='composite'?'selected':''}>RS 综合</option>
      <option value="chg_5d" ${currentSort==='chg_5d'?'selected':''}>5日涨幅</option>
      <option value="chg_15d" ${currentSort==='chg_15d'?'selected':''}>15日涨幅</option>
      <option value="chg_30d" ${currentSort==='chg_30d'?'selected':''}>30日涨幅</option>
      <option value="chg_60d" ${currentSort==='chg_60d'?'selected':''}>60日涨幅</option>
      <option value="flow" ${currentSort==='flow'?'selected':''}>资金积累</option>
      <option value="vol_ratio" ${currentSort==='vol_ratio'?'selected':''}>量比</option>
    </select>
  </div>`;

  // Table
  html += `<div class="tbl-wrap"><table>
    <thead><tr>
      <th>#</th><th>板块</th><th>当前价</th>
      <th onclick="setSort('chg_5d')">5日</th>
      <th onclick="setSort('chg_15d')">15日</th>
      <th onclick="setSort('chg_30d')">30日</th>
      <th onclick="setSort('chg_60d')">60日</th>
      <th onclick="setSort('composite')">RS综合</th>
      <th>资金</th>
      <th onclick="setSort('vol_ratio')">量比</th>
    </tr></thead><tbody>`;

  sectors.forEach((s, i) => {
    const catCls = s.category === 'spdr' ? 'cat-spdr' : 'cat-thematic';
    const catLabel = s.category === 'spdr' ? '行业' : '主题';
    html += `<tr>
      <td class="rank-num">${i + 1}</td>
      <td><div class="sym-cell">
        <span class="sym-ticker">${s.symbol}</span>
        <span class="sym-name">${s.name}</span>
        <span class="cat-badge ${catCls}">${catLabel}</span>
      </div></td>
      <td>$${s.current}</td>
      <td>${chg(s.chg_5d)}</td>
      <td>${chg(s.chg_15d)}</td>
      <td>${chg(s.chg_30d)}</td>
      <td>${chg(s.chg_60d)}</td>
      <td>${rsVal(s.rs?.composite)}</td>
      <td>${flowBadge(s.flow)}</td>
      <td>${s.vol_ratio ?? '-'}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';

  // Flow Panel
  if (inflowETFs.length > 0 || outflowETFs.length > 0) {
    html += '<div class="flow-panel">';
    html += `<div class="flow-section"><h3>资金流入信号 (放量 + 价格上涨)</h3><div class="flow-tags">`;
    inflowETFs.forEach(s => {
      html += `<span class="flow-tag inflow">${s.symbol} ${s.name} ▲${s.flow.vol_surge}x</span>`;
    });
    if (inflowETFs.length === 0) html += '<span style="color:#78909c">暂无</span>';
    html += '</div></div>';
    html += `<div class="flow-section"><h3>资金流出信号 (放量 + 价格下跌)</h3><div class="flow-tags">`;
    outflowETFs.forEach(s => {
      html += `<span class="flow-tag outflow">${s.symbol} ${s.name} ▼${s.flow.vol_surge}x</span>`;
    });
    if (outflowETFs.length === 0) html += '<span style="color:#78909c">暂无</span>';
    html += '</div></div>';
    html += '</div>';
  }

  document.getElementById('content').innerHTML = html;

  // Update timestamp
  if (DATA.generated_at) {
    const d = new Date(DATA.generated_at);
    document.getElementById('updated-at').textContent = '更新: ' + d.toLocaleString('zh-CN');
  }
}

function setFilter(f) { currentFilter = f; render(); }
function setSort(s) { currentSort = s; render(); }

// 初始加载
loadData();
</script>
</body>
</html>"""
