"""回测引擎 + 报告生成"""
import logging
from collections import defaultdict

import numpy as np
import pandas as pd

from app.data.yfinance_provider import YFinanceProvider
from app.backtest.strategies import get_strategy
from db.models import SessionLocal, BacktestRecord

logger = logging.getLogger(__name__)
_yf = YFinanceProvider()


def run_backtest(symbol: str, strategy_name: str, period: str = "1y",
                 initial_capital: float = 100000) -> str:
    """
    运行策略回测

    Args:
        symbol: 股票代码
        strategy_name: 策略名称
        period: 回测数据周期
        initial_capital: 初始资金

    Returns:
        回测报告文本
    """
    strategy = get_strategy(strategy_name)
    df = _yf.get_history(symbol, period)
    if df.empty:
        return f"无法获取 {symbol} 的历史数据"
    if len(df) < 60:
        return f"{symbol} 数据不足 60 条，无法进行有效回测"

    # 生成信号
    signals = strategy.generate_signals(df)

    # 模拟交易
    capital = initial_capital
    position = 0        # 持股数量
    trades = []         # 交易记录
    portfolio_values = []  # 每日组合价值

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = signals.iloc[i]

        if signal == 1 and position == 0:
            # 买入（全仓）
            shares = int(capital / price)
            if shares > 0:
                cost = shares * price
                capital -= cost
                position = shares
                trades.append({
                    'date': date, 'action': '买入',
                    'price': price, 'shares': shares, 'value': cost
                })

        elif signal == -1 and position > 0:
            # 卖出（清仓）
            revenue = position * price
            capital += revenue
            trades.append({
                'date': date, 'action': '卖出',
                'price': price, 'shares': position, 'value': revenue
            })
            position = 0

        # 记录每日组合价值
        portfolio_value = capital + position * price
        portfolio_values.append(portfolio_value)

    # 如果还持有，按最后价格平仓计算
    final_price = df['Close'].iloc[-1]
    final_value = capital + position * final_price

    # 计算指标
    total_return = (final_value - initial_capital) / initial_capital * 100
    portfolio_series = pd.Series(portfolio_values, index=df.index)
    daily_returns = portfolio_series.pct_change().dropna()

    # 最大回撤
    cummax = portfolio_series.cummax()
    drawdown = (portfolio_series - cummax) / cummax
    max_drawdown = drawdown.min() * 100

    # 夏普比率 (假设无风险利率 4%)
    if len(daily_returns) > 0 and daily_returns.std() != 0:
        sharpe = (daily_returns.mean() * 252 - 0.04) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0

    # 胜率
    buy_trades = [t for t in trades if t['action'] == '买入']
    sell_trades = [t for t in trades if t['action'] == '卖出']
    win_count = 0
    for i in range(min(len(buy_trades), len(sell_trades))):
        if sell_trades[i]['price'] > buy_trades[i]['price']:
            win_count += 1
    total_trades = min(len(buy_trades), len(sell_trades))
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    # 买入持有对比
    buy_hold_return = (final_price - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100

    # 生成报告
    lines = []
    lines.append(f"{'='*40}")
    lines.append(f"策略回测报告")
    lines.append(f"{'='*40}")
    lines.append(f"股票: {symbol}")
    lines.append(f"策略: {strategy.name}")
    lines.append(f"周期: {period} ({df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')})")
    lines.append(f"初始资金: ${initial_capital:,.0f}")
    lines.append("")
    lines.append("【回测结果】")
    lines.append(f"  最终资产: ${final_value:,.2f}")
    lines.append(f"  总收益率: {total_return:+.2f}%")
    lines.append(f"  买入持有收益: {buy_hold_return:+.2f}%")
    lines.append(f"  超额收益: {total_return - buy_hold_return:+.2f}%")
    lines.append(f"  最大回撤: {max_drawdown:.2f}%")
    lines.append(f"  夏普比率: {sharpe:.2f}")
    lines.append(f"  交易次数: {len(trades)}")
    lines.append(f"  胜率: {win_rate:.1f}%")
    lines.append("")

    if trades:
        lines.append("【最近交易记录】")
        for t in trades[-10:]:
            lines.append(f"  {t['date'].strftime('%Y-%m-%d')} {t['action']} ${t['price']:.2f} x {t['shares']}股")

    lines.append("")
    lines.append("【风险提示】")
    lines.append("  回测结果不代表未来收益，仅供参考。")
    lines.append(f"{'='*40}")

    report = "\n".join(lines)

    # 保存到数据库
    db = SessionLocal()
    try:
        record = BacktestRecord(
            symbol=symbol,
            strategy_name=strategy.name,
            period=period,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            total_trades=len(trades),
            win_rate=win_rate,
            report_text=report,
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save backtest record: {e}")
    finally:
        db.close()

    return report


def run_custom_backtest(symbol: str, signals: list, period: str = "1y",
                        initial_capital: float = 100000,
                        position_mode: str = "full",
                        position_pct: float = 100,
                        fixed_amount: float = 10000) -> dict:
    """执行自定义策略回测，返回结构化 dict 供前端渲染。"""
    df = _yf.get_history(symbol, period)
    if df.empty:
        return {"error": f"无法获取 {symbol} 的历史数据"}
    if len(df) < 60:
        return {"error": f"{symbol} 数据不足 60 条，无法进行有效回测"}
    if len(signals) != len(df):
        return {"error": f"信号长度 ({len(signals)}) 与数据长度 ({len(df)}) 不匹配"}

    # 信号滞后一天：防止 look-ahead bias
    signals = [0] + signals[:-1]

    # --- 交易模拟 ---
    capital = initial_capital
    position = 0
    trades = []
    portfolio_values = []
    buy_date = None
    cumulative_pnl = 0.0
    liquidated = False
    liquidated_msg = ""

    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = signals[i]

        if signal == 1 and position == 0:
            total_assets = capital + position * price
            if position_mode == "percent":
                buy_amount = total_assets * position_pct / 100
            elif position_mode == "fixed":
                buy_amount = min(fixed_amount, capital)
            else:
                buy_amount = capital

            shares = int(buy_amount / price)
            if shares > 0:
                cost = shares * price
                capital -= cost
                position = shares
                buy_date = date
                trades.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'action': 'BUY',
                    'price': round(price, 2),
                    'shares': shares,
                    'value': round(cost, 2),
                    'pnl': 0,
                    'cumulative_pnl': round(cumulative_pnl, 2),
                })

        elif signal == -1 and position > 0:
            revenue = position * price
            last_buy = next(
                (t for t in reversed(trades) if t['action'] == 'BUY'), None
            )
            pnl = revenue - (last_buy['value'] if last_buy else 0)
            cumulative_pnl += pnl
            capital += revenue
            trades.append({
                'date': date.strftime('%Y-%m-%d'),
                'action': 'SELL',
                'price': round(price, 2),
                'shares': position,
                'value': round(revenue, 2),
                'pnl': round(pnl, 2),
                'cumulative_pnl': round(cumulative_pnl, 2),
            })
            position = 0
            buy_date = None

        pv = capital + position * price
        portfolio_values.append(pv)

        # 破产检查
        if pv < initial_capital * 0.2:
            liquidated = True
            liquidated_msg = "策略已触发强平：账户总资产低于初始资金的 20%"
            break

    # --- 基础指标 ---
    actual_len = len(portfolio_values)
    final_price = df['Close'].iloc[actual_len - 1]
    final_value = capital + position * final_price
    total_return = (final_value - initial_capital) / initial_capital * 100

    actual_dates = df.index[:actual_len]
    portfolio_series = pd.Series(portfolio_values, index=actual_dates)
    daily_returns = portfolio_series.pct_change().dropna()

    cummax = portfolio_series.cummax()
    drawdown = (portfolio_series - cummax) / cummax
    max_drawdown = drawdown.min() * 100

    if len(daily_returns) > 0 and daily_returns.std() != 0:
        sharpe = (daily_returns.mean() * 252 - 0.04) / (daily_returns.std() * np.sqrt(252))
    else:
        sharpe = 0

    first_price = df['Close'].iloc[0]
    buy_hold_return = (final_price - first_price) / first_price * 100

    # --- 胜率 & 专业指标 ---
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    paired = min(len(buy_trades), len(sell_trades))

    wins, losses, holding_days_list = [], [], []
    for idx in range(paired):
        pnl = sell_trades[idx]['value'] - buy_trades[idx]['value']
        (wins if pnl > 0 else losses).append(abs(pnl))
        try:
            bd = pd.Timestamp(buy_trades[idx]['date'])
            sd = pd.Timestamp(sell_trades[idx]['date'])
            holding_days_list.append((sd - bd).days)
        except Exception:
            pass

    win_rate = (len(wins) / paired * 100) if paired > 0 else 0
    total_wins = sum(wins)
    total_losses = sum(losses)
    profit_factor = round(total_wins / total_losses, 2) if total_losses > 0 else None
    avg_win = round(total_wins / len(wins), 2) if wins else 0
    avg_loss = round(total_losses / len(losses), 2) if losses else 0
    max_win = round(max(wins), 2) if wins else 0
    max_loss = round(max(losses), 2) if losses else 0
    avg_holding_days = round(
        sum(holding_days_list) / len(holding_days_list), 1
    ) if holding_days_list else 0

    # --- 图表数据 ---
    pv_list, bh_list, dd_list = [], [], []
    bh_shares = initial_capital / first_price
    for idx, date in enumerate(actual_dates):
        ds = date.strftime('%Y-%m-%d')
        pv_list.append({"date": ds, "value": round(portfolio_values[idx], 2)})
        bh_list.append({"date": ds, "value": round(bh_shares * df['Close'].iloc[idx], 2)})
        dd_list.append({"date": ds, "drawdown_pct": round(drawdown.iloc[idx] * 100, 2)})

    price_data = [
        {"date": df.index[i].strftime('%Y-%m-%d'), "close": round(df['Close'].iloc[i], 2)}
        for i in range(len(df))
    ]
    trade_points = [
        {"date": t['date'], "price": t['price'], "action": t['action']}
        for t in trades
    ]

    monthly_returns = _calc_monthly_returns(portfolio_series)

    return {
        "summary": {
            "total_return": round(total_return, 2),
            "buy_hold_return": round(buy_hold_return, 2),
            "excess_return": round(total_return - buy_hold_return, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe": round(sharpe, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": len(trades),
            "final_value": round(final_value, 2),
            "liquidated": liquidated,
            "liquidated_msg": liquidated_msg,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_win": max_win,
            "max_loss": max_loss,
            "avg_holding_days": avg_holding_days,
        },
        "trades": trades,
        "portfolio_values": pv_list,
        "buy_hold_values": bh_list,
        "drawdown_values": dd_list,
        "price_data": price_data,
        "trade_points": trade_points,
        "monthly_returns": monthly_returns,
    }


def _calc_monthly_returns(portfolio_series: pd.Series) -> dict:
    """计算月度收益率分解表。"""
    if len(portfolio_series) < 2:
        return {}

    monthly = defaultdict(dict)
    groups = portfolio_series.groupby([
        portfolio_series.index.year,
        portfolio_series.index.month,
    ])

    prev_month_end = portfolio_series.iloc[0]
    for (year, month), group in groups:
        month_end = group.iloc[-1]
        ret = (month_end - prev_month_end) / prev_month_end * 100
        monthly[str(year)][str(month)] = round(ret, 2)
        prev_month_end = month_end

    yearly_groups = portfolio_series.groupby(portfolio_series.index.year)
    prev_year_end = portfolio_series.iloc[0]
    for year, group in yearly_groups:
        year_end = group.iloc[-1]
        annual_ret = (year_end - prev_year_end) / prev_year_end * 100
        monthly[str(year)]["annual"] = round(annual_ret, 2)
        prev_year_end = year_end

    return dict(monthly)
