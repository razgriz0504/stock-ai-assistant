"""持仓聚合与仓位计算服务.

- 持仓采用平均成本法：买入摊入成本（含佣金），卖出按当时均价结转实现盈亏。
- 仓位计算采用固定风险法：单笔风险额 = 账户 × 风险% ，
  股数 = 风险额 ÷ (入场价 - 止损价)，并受单一持仓市值上限约束。
"""

import logging
import math

logger = logging.getLogger(__name__)


def aggregate_positions(trades: list) -> dict:
    """按平均成本法聚合交易流水.

    trades: TradeRecord 列表（任意顺序，内部按 trade_date + id 排序）。
    返回 {
      "positions": [ {symbol, qty, avg_cost, cost_value, realized_pnl,
                      initial_stop, first_buy_date, last_trade_date} ],
      "closed": [ {symbol, realized_pnl, trades} ],   # 已清仓标的
      "total_realized_pnl": float,
      "warnings": [str],
    }
    """
    warnings: list[str] = []
    # 按 symbol 分组，时间顺序处理
    by_symbol: dict[str, list] = {}
    for t in sorted(trades, key=lambda x: (x.trade_date, x.id)):
        by_symbol.setdefault(t.symbol, []).append(t)

    positions = []
    closed = []
    total_realized = 0.0

    for symbol, ts in by_symbol.items():
        qty = 0.0
        total_cost = 0.0      # 当前持仓总成本（含佣金）
        realized = 0.0
        initial_stop = None   # 持仓期内最近一笔带止损的买入
        first_buy_date = None
        trade_count = 0

        for t in ts:
            trade_count += 1
            if t.side == "buy":
                if qty <= 0:
                    # 新开仓，重置持仓期元数据
                    first_buy_date = t.trade_date
                    initial_stop = None
                total_cost += t.qty * t.price + (t.commission or 0.0)
                qty += t.qty
                if t.initial_stop:
                    initial_stop = t.initial_stop
            else:  # sell
                if qty <= 0:
                    warnings.append(f"{symbol} 在 {t.trade_date} 无持仓却有卖出记录，已忽略")
                    continue
                sell_qty = min(t.qty, qty)
                if t.qty > qty:
                    warnings.append(f"{symbol} 在 {t.trade_date} 卖出量超过持仓，按持仓量 {qty:g} 结算")
                avg_cost = total_cost / qty
                realized += sell_qty * (t.price - avg_cost) - (t.commission or 0.0)
                qty -= sell_qty
                total_cost = avg_cost * qty
                if qty <= 1e-9:
                    qty = 0.0
                    total_cost = 0.0

        total_realized += realized
        if qty > 0:
            positions.append({
                "symbol": symbol,
                "qty": round(qty, 4),
                "avg_cost": round(total_cost / qty, 4),
                "cost_value": round(total_cost, 2),
                "realized_pnl": round(realized, 2),
                "initial_stop": initial_stop,
                "first_buy_date": first_buy_date,
                "last_trade_date": ts[-1].trade_date,
                "trade_count": trade_count,
            })
        elif trade_count > 0:
            closed.append({
                "symbol": symbol,
                "realized_pnl": round(realized, 2),
                "trades": trade_count,
                "last_trade_date": ts[-1].trade_date,
            })

    positions.sort(key=lambda p: -p["cost_value"])
    closed.sort(key=lambda p: p["last_trade_date"], reverse=True)
    return {
        "positions": positions,
        "closed": closed,
        "total_realized_pnl": round(total_realized, 2),
        "warnings": warnings,
    }


def suggest_position_size(
    account_size: float,
    risk_pct: float,
    entry: float,
    stop: float,
    max_position_pct: float = 25.0,
) -> dict:
    """固定风险法仓位建议.

    返回 {shares, position_value, position_pct, risk_amount, risk_per_share,
          stop_distance_pct, capped, warnings}
    """
    warnings: list[str] = []
    if entry <= 0 or stop <= 0:
        raise ValueError("入场价与止损价必须为正数")
    if stop >= entry:
        raise ValueError("止损价必须低于入场价（做多）")
    if account_size <= 0:
        raise ValueError("账户资金必须为正数")

    risk_per_share = entry - stop
    stop_distance_pct = risk_per_share / entry * 100
    risk_amount = account_size * risk_pct / 100.0
    shares = math.floor(risk_amount / risk_per_share)

    if stop_distance_pct > 10:
        warnings.append(f"止损距离 {stop_distance_pct:.1f}% 偏宽（Minervini 建议 ≤10%，理想 5-8%）")

    # 单一持仓市值上限约束
    capped = False
    max_value = account_size * max_position_pct / 100.0
    if shares * entry > max_value:
        shares = math.floor(max_value / entry)
        capped = True
        warnings.append(f"仓位受单一持仓上限 {max_position_pct:.0f}% 约束，"
                        f"实际风险将低于设定值")

    position_value = shares * entry
    return {
        "shares": int(shares),
        "position_value": round(position_value, 2),
        "position_pct": round(position_value / account_size * 100, 2),
        "risk_amount": round(shares * risk_per_share, 2),
        "risk_pct_used": round(shares * risk_per_share / account_size * 100, 3),
        "risk_per_share": round(risk_per_share, 4),
        "stop_distance_pct": round(stop_distance_pct, 2),
        "capped": capped,
        "warnings": warnings,
    }
