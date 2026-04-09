"""预警规则定义"""
import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class AlertCondition:
    condition_type: str  # price_above, price_below, change_pct_above, change_pct_below
    threshold: float
    description: str


def parse_alert_condition(text: str) -> Optional[AlertCondition]:
    """
    解析用户输入的监控条件

    支持格式:
    - "跌破150" / "低于150"  -> price_below 150
    - "突破200" / "高于200"  -> price_above 200
    - "涨幅超过5%"            -> change_pct_above 5
    - "跌幅超过3%"            -> change_pct_below -3
    """
    text = text.strip()

    # 跌破/低于
    m = re.match(r'(跌破|低于|下破)\s*(\d+\.?\d*)', text)
    if m:
        val = float(m.group(2))
        return AlertCondition("price_below", val, f"价格跌破 ${val:.2f}")

    # 突破/高于
    m = re.match(r'(突破|高于|上破|涨到)\s*(\d+\.?\d*)', text)
    if m:
        val = float(m.group(2))
        return AlertCondition("price_above", val, f"价格突破 ${val:.2f}")

    # 涨幅超过 X%
    m = re.match(r'涨幅超过\s*(\d+\.?\d*)%?', text)
    if m:
        val = float(m.group(1))
        return AlertCondition("change_pct_above", val, f"涨幅超过 {val}%")

    # 跌幅超过 X%
    m = re.match(r'跌幅超过\s*(\d+\.?\d*)%?', text)
    if m:
        val = float(m.group(1))
        return AlertCondition("change_pct_below", -val, f"跌幅超过 {val}%")

    return None
