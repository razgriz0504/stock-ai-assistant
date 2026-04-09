"""回测引擎 + 报告生成"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime

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
    try:
        db = SessionLocal()
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
        db.close()
    except Exception as e:
        logger.error(f"Failed to save backtest record: {e}")

    return report
