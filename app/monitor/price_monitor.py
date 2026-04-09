"""价格监控引擎 - 规则管理 + 条件检测"""
import logging
from datetime import datetime
from typing import Optional

from db.models import SessionLocal, MonitorRule
from app.monitor.alert_rules import parse_alert_condition
from app.data.finnhub_provider import FinnhubProvider
from app.data.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

# 数据源: 优先 Finnhub（实时），回退 yfinance
_finnhub = FinnhubProvider()
_yfinance = YFinanceProvider()


def _get_price(symbol: str) -> Optional[float]:
    """获取实时价格，优先 Finnhub"""
    quote = _finnhub.get_realtime_quote(symbol)
    if quote and quote.price > 0:
        return quote.price
    quote = _yfinance.get_realtime_quote(symbol)
    if quote and quote.price > 0:
        return quote.price
    return None


def add_monitor_rule(symbol: str, condition_text: str, user_id: str, chat_id: str) -> str:
    """添加监控规则"""
    condition = parse_alert_condition(condition_text)
    if not condition:
        return (f"无法识别监控条件: {condition_text}\n"
                "支持的格式:\n"
                "  跌破150 / 低于150\n"
                "  突破200 / 高于200\n"
                "  涨幅超过5% / 跌幅超过3%")

    db = SessionLocal()
    try:
        rule = MonitorRule(
            symbol=symbol.upper(),
            condition_type=condition.condition_type,
            threshold=condition.threshold,
            is_active=True,
            feishu_user_id=user_id,
            description=f"{symbol} {condition.description}",
        )
        db.add(rule)
        db.commit()

        current_price = _get_price(symbol)
        price_info = f" (当前价格: ${current_price:.2f})" if current_price else ""

        return f"监控已设置: {symbol} {condition.description}{price_info}\n规则ID: {rule.id}"
    finally:
        db.close()


def remove_monitor_rules(symbol: str, user_id: str) -> str:
    """取消某只股票的所有监控"""
    db = SessionLocal()
    try:
        rules = db.query(MonitorRule).filter(
            MonitorRule.symbol == symbol.upper(),
            MonitorRule.feishu_user_id == user_id,
            MonitorRule.is_active == True,
        ).all()

        if not rules:
            return f"没有找到 {symbol} 的活跃监控规则"

        for rule in rules:
            rule.is_active = False
        db.commit()
        return f"已取消 {symbol} 的 {len(rules)} 条监控规则"
    finally:
        db.close()


def list_user_monitors(user_id: str) -> str:
    """列出用户所有活跃监控"""
    db = SessionLocal()
    try:
        rules = db.query(MonitorRule).filter(
            MonitorRule.feishu_user_id == user_id,
            MonitorRule.is_active == True,
        ).all()

        if not rules:
            return "当前没有活跃的监控规则。\n发送 /监控 AAPL 跌破150 来添加。"

        lines = ["当前监控列表:"]
        for rule in rules:
            lines.append(f"  [{rule.id}] {rule.description}")
        return "\n".join(lines)
    finally:
        db.close()


def check_all_monitors() -> list[dict]:
    """
    检查所有活跃监控规则，返回触发的规则列表。
    由 scheduler 定时调用。
    """
    db = SessionLocal()
    triggered = []
    try:
        rules = db.query(MonitorRule).filter(MonitorRule.is_active == True).all()
        if not rules:
            return triggered

        # 按 symbol 分组，避免重复请求
        symbols = set(r.symbol for r in rules)
        prices = {}
        for symbol in symbols:
            price = _get_price(symbol)
            if price:
                prices[symbol] = price

        for rule in rules:
            price = prices.get(rule.symbol)
            if price is None:
                continue

            is_triggered = False
            if rule.condition_type == "price_below" and price <= rule.threshold:
                is_triggered = True
            elif rule.condition_type == "price_above" and price >= rule.threshold:
                is_triggered = True
            # change_pct 需要昨日收盘价，简化处理
            # TODO: 后续可增加涨跌幅监控

            if is_triggered:
                rule.is_active = False  # 触发后自动关闭
                rule.triggered_at = datetime.utcnow()
                triggered.append({
                    "rule_id": rule.id,
                    "symbol": rule.symbol,
                    "description": rule.description,
                    "current_price": price,
                    "user_id": rule.feishu_user_id,
                })

        db.commit()
    except Exception as e:
        logger.error(f"Monitor check error: {e}", exc_info=True)
    finally:
        db.close()

    return triggered
