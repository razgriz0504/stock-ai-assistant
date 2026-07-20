"""策略回测 REST API（前端 SPA: BacktestPage.tsx）"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.data.yfinance_provider import YFinanceProvider
from app.backtest.sandbox import run_user_strategy
from app.backtest.engine import run_custom_backtest

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])
_yf = YFinanceProvider()


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
