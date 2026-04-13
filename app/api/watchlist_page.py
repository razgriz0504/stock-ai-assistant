"""关注列表管理页面"""
import json
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from db.models import SessionLocal, UserPreference

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_USER_ID = "web_default"


class WatchlistUpdate(BaseModel):
    stocks: list


@router.get("/api/watchlist")
async def get_watchlist():
    """获取当前关注列表"""
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        if pref and pref.watchlist:
            stocks = json.loads(pref.watchlist)
        else:
            stocks = []
        return {"stocks": stocks}
    finally:
        db.close()


@router.post("/api/watchlist")
async def update_watchlist(req: WatchlistUpdate):
    """更新关注列表"""
    # 去重、转大写、过滤空值
    stocks = list(dict.fromkeys(s.strip().upper() for s in req.stocks if s.strip()))
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        if not pref:
            pref = UserPreference(feishu_user_id=WEB_USER_ID, watchlist=json.dumps(stocks))
            db.add(pref)
        else:
            pref.watchlist = json.dumps(stocks)
        db.commit()
        return {"success": True, "stocks": stocks}
    finally:
        db.close()


@router.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page():
    return _build_html()


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>关注列表</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }
h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
.subtitle { color: #78909c; font-size: 13px; margin-bottom: 24px; }
.subtitle a { color: #4fc3f7; text-decoration: none; }
.subtitle a:hover { text-decoration: underline; }
.input-row { display: flex; gap: 10px; margin-bottom: 20px; }
.input-row input {
    flex: 1; background: #1a2634; border: 1px solid #2a3a4a; color: #e0e0e0;
    padding: 10px 14px; border-radius: 6px; font-size: 14px;
}
.input-row input:focus { border-color: #4fc3f7; outline: none; }
.input-row input::placeholder { color: #546e7a; }
.btn {
    background: #4fc3f7; color: #0f1923; border: none; padding: 10px 20px;
    border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
    white-space: nowrap;
}
.btn:hover { background: #81d4fa; }
.stock-list { margin-bottom: 20px; }
.stock-item {
    display: flex; align-items: center; justify-content: space-between;
    background: #1a2634; border: 1px solid #2a3a4a; border-radius: 6px;
    padding: 10px 16px; margin-bottom: 8px;
}
.stock-item .symbol { font-size: 15px; font-weight: 600; color: #e0e0e0; letter-spacing: 1px; }
.del-btn {
    background: none; border: none; color: #ef5350; font-size: 18px;
    cursor: pointer; padding: 2px 8px; border-radius: 4px;
}
.del-btn:hover { background: rgba(239,83,80,0.15); }
.empty-msg { color: #546e7a; font-size: 14px; padding: 20px 0; text-align: center; }
.status-msg { margin-top: 12px; font-size: 13px; min-height: 20px; }
.status-msg.ok { color: #66bb6a; }
.status-msg.err { color: #ef5350; }
.count { color: #78909c; font-size: 13px; margin-bottom: 12px; }
</style>
</head>
<body>
<h1>Watchlist</h1>
<p class="subtitle">管理你的关注股票列表 | <a href="/scoring">前往选股打分 &rarr;</a></p>

<div class="input-row">
    <input type="text" id="stock-input" placeholder="输入股票代码，多个用逗号分隔（如 AAPL, TSLA, NVDA）"
           onkeydown="if(event.key==='Enter')addStocks()">
    <button class="btn" onclick="addStocks()">添加</button>
</div>

<div class="count" id="count"></div>
<div class="stock-list" id="stock-list"></div>
<div class="status-msg" id="status"></div>

<script>
let stocks = [];

async function loadStocks() {
    try {
        const resp = await fetch('/api/watchlist');
        const data = await resp.json();
        stocks = data.stocks || [];
        render();
    } catch(e) {
        showStatus('加载失败: ' + e.message, 'err');
    }
}

function render() {
    const list = document.getElementById('stock-list');
    const count = document.getElementById('count');
    count.textContent = stocks.length > 0 ? `共 ${stocks.length} 只股票` : '';

    if (stocks.length === 0) {
        list.innerHTML = '<div class="empty-msg">暂无关注股票，请在上方添加</div>';
        return;
    }
    list.innerHTML = stocks.map((s, i) =>
        `<div class="stock-item">
            <span class="symbol">${s}</span>
            <button class="del-btn" onclick="removeStock(${i})" title="删除">&times;</button>
        </div>`
    ).join('');
}

function addStocks() {
    const input = document.getElementById('stock-input');
    const val = input.value.trim();
    if (!val) return;

    const newStocks = val.split(/[,，\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
    const added = [];
    for (const s of newStocks) {
        if (!stocks.includes(s)) {
            stocks.push(s);
            added.push(s);
        }
    }
    input.value = '';
    render();
    saveStocks();
    if (added.length > 0) {
        showStatus(`已添加: ${added.join(', ')}`, 'ok');
    } else {
        showStatus('股票已在列表中', 'err');
    }
}

function removeStock(idx) {
    const removed = stocks.splice(idx, 1);
    render();
    saveStocks();
    showStatus(`已移除: ${removed[0]}`, 'ok');
}

async function saveStocks() {
    try {
        const resp = await fetch('/api/watchlist', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({stocks: stocks}),
        });
        const data = await resp.json();
        if (data.success) {
            stocks = data.stocks;
            render();
        }
    } catch(e) {
        showStatus('保存失败: ' + e.message, 'err');
    }
}

function showStatus(msg, type) {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.className = 'status-msg ' + type;
    setTimeout(() => { el.textContent = ''; el.className = 'status-msg'; }, 3000);
}

loadStocks();
</script>
</body>
</html>"""
