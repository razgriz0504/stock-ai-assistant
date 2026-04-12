"""策略回测页面 - 路由 + 内联 HTML"""
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.data.yfinance_provider import YFinanceProvider
from app.backtest.sandbox import run_user_strategy
from app.backtest.engine import run_custom_backtest

logger = logging.getLogger(__name__)
router = APIRouter()
_yf = YFinanceProvider()

DEFAULT_STRATEGY = '''def strategy(data):
    """均线交叉策略：MA5 上穿 MA20 买入，下穿卖出"""
    import pandas as pd
    ma5 = data['Close'].rolling(5).mean()
    ma20 = data['Close'].rolling(20).mean()
    signals = pd.Series(0, index=data.index)
    signals[(ma5 > ma20) & (ma5.shift(1) <= ma20.shift(1))] = 1
    signals[(ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))] = -1
    return signals'''


class BacktestRequest(BaseModel):
    code: str
    symbol: str
    period: str = "1y"
    initial_capital: float = 100000
    position_mode: str = "full"
    position_pct: float = 100
    fixed_amount: float = 10000


@router.post("/api/backtest/run")
async def run_backtest_api(req: BacktestRequest):
    """执行用户策略回测"""
    symbol = req.symbol.strip().upper()
    if not symbol:
        return {"success": False, "error": "请输入股票代码"}

    # 获取历史数据
    df = _yf.get_history(symbol, req.period)
    if df.empty:
        return {"success": False, "error": f"无法获取 {symbol} 的历史数据，请检查股票代码"}
    if len(df) < 60:
        return {"success": False, "error": f"{symbol} 数据不足 60 条，无法进行有效回测"}

    # 准备传给沙箱的 DataFrame（重置索引，Date 列为字符串）
    sandbox_df = df.copy()
    sandbox_df['Date'] = sandbox_df.index.strftime('%Y-%m-%d')
    sandbox_df = sandbox_df.reset_index(drop=True)
    sandbox_df = sandbox_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]

    # 沙箱执行
    result = run_user_strategy(req.code, sandbox_df)
    if not result["success"]:
        return {"success": False, "error": result["error"]}

    # 引擎回测
    bt_result = run_custom_backtest(
        symbol=symbol,
        signals=result["signals"],
        period=req.period,
        initial_capital=req.initial_capital,
        position_mode=req.position_mode,
        position_pct=req.position_pct,
        fixed_amount=req.fixed_amount,
    )

    if "error" in bt_result:
        return {"success": False, "error": bt_result["error"]}

    return {"success": True, "result": bt_result}


@router.get("/backtest", response_class=HTMLResponse)
async def backtest_page():
    """回测页面"""
    return _build_html()


def _build_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>策略回测</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }}
h1 {{ color: #4fc3f7; margin-bottom: 20px; font-size: 24px; }}
.params {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 16px; }}
.param-group {{ display: flex; flex-direction: column; gap: 4px; }}
.param-group label {{ font-size: 12px; color: #90a4ae; }}
.param-group input, .param-group select {{
    background: #1a2634; border: 1px solid #2a3a4a; color: #e0e0e0;
    padding: 8px 12px; border-radius: 6px; font-size: 14px; min-width: 120px;
}}
.param-group input:focus, .param-group select:focus {{ border-color: #4fc3f7; outline: none; }}
.code-area {{ margin-bottom: 16px; }}
.code-area label {{ font-size: 12px; color: #90a4ae; display: block; margin-bottom: 4px; }}
#code-editor {{
    width: 100%; min-height: 260px; background: #0d1117; border: 1px solid #2a3a4a;
    color: #c9d1d9; padding: 12px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px; line-height: 1.5; resize: vertical; tab-size: 4;
}}
#code-editor:focus {{ border-color: #4fc3f7; outline: none; }}
.run-btn {{
    background: #4fc3f7; color: #0f1923; border: none; padding: 10px 32px;
    border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer; margin-bottom: 20px;
}}
.run-btn:hover {{ background: #81d4fa; }}
.run-btn:disabled {{ background: #37474f; color: #607d8b; cursor: not-allowed; }}
.error-box {{
    background: #1a0000; border: 1px solid #d32f2f; border-radius: 6px; padding: 16px;
    font-family: monospace; font-size: 13px; color: #ef9a9a; white-space: pre-wrap;
    margin-bottom: 20px; display: none;
}}
.liquidated-box {{
    background: #1a0a00; border: 1px solid #ff6f00; border-radius: 6px; padding: 12px 16px;
    color: #ffb74d; font-weight: 600; margin-bottom: 16px; display: none;
}}
#result-area {{ display: none; }}
.summary-grid {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
}}
.summary-card {{
    background: #1a2634; border-radius: 8px; padding: 14px;
    text-align: center; border: 1px solid #2a3a4a;
}}
.summary-card .label {{ font-size: 11px; color: #78909c; margin-bottom: 6px; }}
.summary-card .value {{ font-size: 18px; font-weight: 700; }}
.positive {{ color: #66bb6a; }}
.negative {{ color: #ef5350; }}
.neutral {{ color: #4fc3f7; }}
.chart-box {{ background: #1a2634; border-radius: 8px; padding: 16px; margin-bottom: 20px; border: 1px solid #2a3a4a; }}
.chart-box h3 {{ color: #90a4ae; font-size: 14px; margin-bottom: 12px; }}
.chart {{ width: 100%; height: 350px; }}
.chart-small {{ width: 100%; height: 200px; }}
.monthly-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
.monthly-table th, .monthly-table td {{
    padding: 8px 10px; text-align: center; border: 1px solid #2a3a4a;
}}
.monthly-table th {{ background: #1a2634; color: #90a4ae; font-weight: 600; }}
.monthly-table td {{ background: #0f1923; }}
.trades-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.trades-table th {{ background: #1a2634; color: #90a4ae; padding: 10px; text-align: left; border-bottom: 2px solid #2a3a4a; }}
.trades-table td {{ padding: 8px 10px; border-bottom: 1px solid #1a2634; }}
.trades-table tr:hover {{ background: #1a2634; }}
.hidden {{ display: none; }}
@media (max-width: 768px) {{
    .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .params {{ flex-direction: column; }}
}}
</style>
</head>
<body>
<h1>Strategy Backtest</h1>

<div class="params">
    <div class="param-group">
        <label>股票代码</label>
        <input type="text" id="symbol" value="AAPL" placeholder="如 AAPL, TSLA">
    </div>
    <div class="param-group">
        <label>时间范围</label>
        <select id="period">
            <option value="3mo">3 个月</option>
            <option value="6mo">6 个月</option>
            <option value="1y" selected>1 年</option>
            <option value="2y">2 年</option>
            <option value="3y">3 年</option>
        </select>
    </div>
    <div class="param-group">
        <label>初始资金 ($)</label>
        <input type="number" id="capital" value="100000" min="1000" step="1000">
    </div>
    <div class="param-group">
        <label>仓位模式</label>
        <select id="position-mode" onchange="onPositionModeChange()">
            <option value="full">全仓</option>
            <option value="percent">固定比例</option>
            <option value="fixed">固定金额</option>
        </select>
    </div>
    <div class="param-group hidden" id="pct-group">
        <label>买入比例 (%)</label>
        <input type="number" id="position-pct" value="10" min="1" max="100" step="1">
    </div>
    <div class="param-group hidden" id="fixed-group">
        <label>买入金额 ($)</label>
        <input type="number" id="fixed-amount" value="10000" min="100" step="100">
    </div>
</div>

<div class="code-area">
    <label>策略代码（Python）</label>
    <textarea id="code-editor">{DEFAULT_STRATEGY}</textarea>
</div>

<button class="run-btn" id="run-btn" onclick="runBacktest()">运行回测</button>

<div class="error-box" id="error-box"></div>
<div class="liquidated-box" id="liquidated-box"></div>

<div id="result-area">
    <div class="summary-grid" id="summary-grid"></div>

    <div class="chart-box">
        <h3>价格走势 & 买卖标记</h3>
        <div class="chart" id="price-chart"></div>
    </div>
    <div class="chart-box">
        <h3>策略收益 vs 买入持有</h3>
        <div class="chart" id="equity-chart"></div>
    </div>
    <div class="chart-box">
        <h3>回撤曲线</h3>
        <div class="chart-small" id="drawdown-chart"></div>
    </div>

    <div class="chart-box">
        <h3>月度收益分解 (%)</h3>
        <div id="monthly-table-container"></div>
    </div>

    <div class="chart-box">
        <h3>交易记录</h3>
        <div id="trades-container" style="max-height:400px;overflow-y:auto;"></div>
    </div>
</div>

<script>
// Tab 键支持
document.getElementById('code-editor').addEventListener('keydown', function(e) {{
    if (e.key === 'Tab') {{
        e.preventDefault();
        const s = this.selectionStart, end = this.selectionEnd;
        this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = s + 4;
    }}
}});

function onPositionModeChange() {{
    const mode = document.getElementById('position-mode').value;
    document.getElementById('pct-group').classList.toggle('hidden', mode !== 'percent');
    document.getElementById('fixed-group').classList.toggle('hidden', mode !== 'fixed');
}}

async function runBacktest() {{
    const btn = document.getElementById('run-btn');
    const errBox = document.getElementById('error-box');
    const liqBox = document.getElementById('liquidated-box');
    const resultArea = document.getElementById('result-area');

    btn.disabled = true;
    btn.textContent = '运行中...';
    errBox.style.display = 'none';
    liqBox.style.display = 'none';
    resultArea.style.display = 'none';

    const body = {{
        code: document.getElementById('code-editor').value,
        symbol: document.getElementById('symbol').value,
        period: document.getElementById('period').value,
        initial_capital: parseFloat(document.getElementById('capital').value) || 100000,
        position_mode: document.getElementById('position-mode').value,
        position_pct: parseFloat(document.getElementById('position-pct').value) || 10,
        fixed_amount: parseFloat(document.getElementById('fixed-amount').value) || 10000,
    }};

    try {{
        const resp = await fetch('/api/backtest/run', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
        }});
        const data = await resp.json();

        if (!data.success) {{
            errBox.textContent = data.error;
            errBox.style.display = 'block';
            return;
        }}

        const r = data.result;

        // 强平警告
        if (r.summary.liquidated) {{
            liqBox.textContent = r.summary.liquidated_msg;
            liqBox.style.display = 'block';
        }}

        renderSummary(r.summary);
        renderPriceChart(r.price_data, r.trade_points);
        renderEquityChart(r.portfolio_values, r.buy_hold_values);
        renderDrawdownChart(r.drawdown_values);
        renderMonthlyTable(r.monthly_returns);
        renderTrades(r.trades);
        resultArea.style.display = 'block';

    }} catch (e) {{
        errBox.textContent = '请求失败: ' + e.message;
        errBox.style.display = 'block';
    }} finally {{
        btn.disabled = false;
        btn.textContent = '运行回测';
    }}
}}

function fmtVal(v, suffix) {{
    if (v === null || v === undefined) return '-';
    return (typeof v === 'number' ? v.toLocaleString('en-US', {{maximumFractionDigits: 2}}) : v) + (suffix || '');
}}

function colorClass(v) {{
    if (v === null || v === undefined) return 'neutral';
    return v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral';
}}

function renderSummary(s) {{
    const items = [
        ['总收益率', s.total_return, '%'],
        ['买入持有', s.buy_hold_return, '%'],
        ['超额收益', s.excess_return, '%'],
        ['最大回撤', s.max_drawdown, '%'],
        ['夏普比率', s.sharpe, ''],
        ['胜率', s.win_rate, '%'],
        ['盈亏比 (PF)', s.profit_factor, ''],
        ['交易次数', s.total_trades, ''],
        ['平均盈利', s.avg_win, '$'],
        ['平均亏损', s.avg_loss, '$'],
        ['最大单笔盈利', s.max_win, '$'],
        ['最大单笔亏损', s.max_loss, '$'],
        ['平均持仓天数', s.avg_holding_days, '天'],
        ['最终资产', s.final_value, '$'],
    ];
    const grid = document.getElementById('summary-grid');
    grid.innerHTML = items.map(([label, val, unit]) => {{
        let cls = 'neutral';
        if (['总收益率','超额收益','买入持有'].includes(label)) cls = colorClass(val);
        if (label === '最大回撤') cls = 'negative';
        const display = unit === '$' ? '$' + fmtVal(val, '') : fmtVal(val, unit);
        return `<div class="summary-card"><div class="label">${{label}}</div><div class="value ${{cls}}">${{display}}</div></div>`;
    }}).join('');
}}

function renderPriceChart(priceData, tradePoints) {{
    const chart = echarts.init(document.getElementById('price-chart'));
    const dates = priceData.map(d => d.date);
    const prices = priceData.map(d => d.close);
    const buys = tradePoints.filter(t => t.action === 'BUY').map(t => ({{
        coord: [t.date, t.price],
        symbol: 'triangle', symbolSize: 12, symbolRotate: 0,
        itemStyle: {{ color: '#66bb6a' }}
    }}));
    const sells = tradePoints.filter(t => t.action === 'SELL').map(t => ({{
        coord: [t.date, t.price],
        symbol: 'triangle', symbolSize: 12, symbolRotate: 180,
        itemStyle: {{ color: '#ef5350' }}
    }}));

    chart.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{ trigger: 'axis' }},
        xAxis: {{ type: 'category', data: dates, axisLabel: {{ color: '#78909c' }}, axisLine: {{ lineStyle: {{ color: '#2a3a4a' }} }} }},
        yAxis: {{ type: 'value', scale: true, axisLabel: {{ color: '#78909c' }}, splitLine: {{ lineStyle: {{ color: '#1e2d3d' }} }} }},
        series: [{{
            type: 'line', data: prices, symbol: 'none', lineStyle: {{ color: '#4fc3f7', width: 1.5 }},
            markPoint: {{ data: [...buys, ...sells], label: {{ show: false }} }}
        }}],
        grid: {{ left: 60, right: 20, top: 20, bottom: 40 }},
    }});
    window.addEventListener('resize', () => chart.resize());
}}

function renderEquityChart(portfolio, buyHold) {{
    const chart = echarts.init(document.getElementById('equity-chart'));
    const dates = portfolio.map(d => d.date);
    chart.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{ trigger: 'axis' }},
        legend: {{ data: ['策略收益', '买入持有'], textStyle: {{ color: '#90a4ae' }}, top: 0 }},
        xAxis: {{ type: 'category', data: dates, axisLabel: {{ color: '#78909c' }}, axisLine: {{ lineStyle: {{ color: '#2a3a4a' }} }} }},
        yAxis: {{ type: 'value', scale: true, axisLabel: {{ color: '#78909c', formatter: v => '$' + (v/1000).toFixed(0) + 'k' }}, splitLine: {{ lineStyle: {{ color: '#1e2d3d' }} }} }},
        series: [
            {{ name: '策略收益', type: 'line', data: portfolio.map(d => d.value), symbol: 'none', lineStyle: {{ color: '#4fc3f7', width: 2 }} }},
            {{ name: '买入持有', type: 'line', data: buyHold.map(d => d.value), symbol: 'none', lineStyle: {{ color: '#78909c', width: 1.5, type: 'dashed' }} }},
        ],
        grid: {{ left: 70, right: 20, top: 35, bottom: 40 }},
    }});
    window.addEventListener('resize', () => chart.resize());
}}

function renderDrawdownChart(ddData) {{
    const chart = echarts.init(document.getElementById('drawdown-chart'));
    const dates = ddData.map(d => d.date);
    const values = ddData.map(d => d.drawdown_pct);
    chart.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{ trigger: 'axis', formatter: p => p[0].axisValue + '<br/>回撤: ' + p[0].value.toFixed(2) + '%' }},
        xAxis: {{ type: 'category', data: dates, axisLabel: {{ color: '#78909c' }}, axisLine: {{ lineStyle: {{ color: '#2a3a4a' }} }} }},
        yAxis: {{ type: 'value', inverse: true, axisLabel: {{ color: '#78909c', formatter: v => v.toFixed(0) + '%' }}, splitLine: {{ lineStyle: {{ color: '#1e2d3d' }} }} }},
        series: [{{
            type: 'line', data: values, symbol: 'none',
            lineStyle: {{ color: '#ef5350', width: 1 }},
            areaStyle: {{ color: 'rgba(239,83,80,0.15)' }},
        }}],
        grid: {{ left: 60, right: 20, top: 10, bottom: 30 }},
    }});
    window.addEventListener('resize', () => chart.resize());
}}

function renderMonthlyTable(mr) {{
    const container = document.getElementById('monthly-table-container');
    const years = Object.keys(mr).sort();
    if (!years.length) {{ container.innerHTML = '<p style="color:#607d8b">数据不足，无法生成月度分解</p>'; return; }}

    const months = ['1','2','3','4','5','6','7','8','9','10','11','12'];
    let html = '<table class="monthly-table"><thead><tr><th>年份</th>';
    months.forEach(m => html += `<th>${{m}}月</th>`);
    html += '<th>年度</th></tr></thead><tbody>';

    years.forEach(y => {{
        html += `<tr><td style="font-weight:600">${{y}}</td>`;
        months.forEach(m => {{
            const v = mr[y] && mr[y][m];
            if (v !== undefined && v !== null) {{
                const bg = v > 0 ? `rgba(102,187,106,${{Math.min(Math.abs(v)/10, 0.5)}})` :
                           v < 0 ? `rgba(239,83,80,${{Math.min(Math.abs(v)/10, 0.5)}})` : 'transparent';
                html += `<td style="background:${{bg}}">${{v.toFixed(1)}}</td>`;
            }} else {{
                html += '<td style="color:#37474f">-</td>';
            }}
        }});
        const annual = mr[y] && mr[y]['annual'];
        if (annual !== undefined) {{
            const cls = annual > 0 ? 'positive' : annual < 0 ? 'negative' : '';
            html += `<td class="${{cls}}" style="font-weight:600">${{annual.toFixed(1)}}%</td>`;
        }} else {{
            html += '<td>-</td>';
        }}
        html += '</tr>';
    }});
    html += '</tbody></table>';
    container.innerHTML = html;
}}

function renderTrades(trades) {{
    const container = document.getElementById('trades-container');
    if (!trades.length) {{ container.innerHTML = '<p style="color:#607d8b">无交易记录</p>'; return; }}
    let html = '<table class="trades-table"><thead><tr><th>日期</th><th>操作</th><th>价格</th><th>数量</th><th>金额</th><th>单笔盈亏</th><th>累计盈亏</th></tr></thead><tbody>';
    trades.forEach(t => {{
        const actionColor = t.action === 'BUY' ? '#66bb6a' : '#ef5350';
        const actionText = t.action === 'BUY' ? '买入' : '卖出';
        const pnlCls = t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : '';
        const cumCls = t.cumulative_pnl > 0 ? 'positive' : t.cumulative_pnl < 0 ? 'negative' : '';
        html += `<tr>
            <td>${{t.date}}</td>
            <td style="color:${{actionColor}};font-weight:600">${{actionText}}</td>
            <td>${{t.price.toFixed(2)}}</td>
            <td>${{t.shares}}</td>
            <td>${{t.value.toLocaleString('en-US', {{style:'currency',currency:'USD'}})}}</td>
            <td class="${{pnlCls}}">${{t.pnl ? '$' + t.pnl.toLocaleString('en-US', {{maximumFractionDigits:2}}) : '-'}}</td>
            <td class="${{cumCls}}">${{t.cumulative_pnl ? '$' + t.cumulative_pnl.toLocaleString('en-US', {{maximumFractionDigits:2}}) : '-'}}</td>
        </tr>`;
    }});
    html += '</tbody></table>';
    container.innerHTML = html;
}}
</script>
</body>
</html>"""
