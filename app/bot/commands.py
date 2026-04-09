"""命令定义 - 解析用户输入，返回结构化命令"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedCommand:
    command: str           # 命令类型
    symbol: Optional[str] = None
    args: Optional[str] = None


HELP_TEXT = """支持的命令:

/分析 AAPL     - 量价分析 + AI 建议
/k线 AAPL      - 生成技术指标图表
/监控 AAPL 跌破150  - 设置价格预警
/取消监控 AAPL  - 取消该股票的监控
/回测 均线交叉 AAPL  - 策略回测
/持仓           - 查看当前监控列表
/模型 gpt-4o    - 切换 AI 模型
/帮助           - 显示此帮助

也可以直接提问，例如:
"INTC 现在能抄底吗？"
"帮我分析一下特斯拉最近的走势" """


def parse_command(text: str) -> ParsedCommand:
    """解析用户输入为结构化命令"""
    text = text.strip()

    # /分析 AAPL
    m = re.match(r'^/分析\s+([A-Za-z]+)', text)
    if m:
        return ParsedCommand(command="analyze", symbol=m.group(1).upper())

    # /k线 AAPL
    m = re.match(r'^/[kK]线\s+([A-Za-z]+)', text)
    if m:
        return ParsedCommand(command="chart", symbol=m.group(1).upper())

    # /监控 AAPL 跌破150
    m = re.match(r'^/监控\s+([A-Za-z]+)\s+(.+)', text)
    if m:
        return ParsedCommand(command="monitor", symbol=m.group(1).upper(), args=m.group(2))

    # /取消监控 AAPL
    m = re.match(r'^/取消监控\s+([A-Za-z]+)', text)
    if m:
        return ParsedCommand(command="cancel_monitor", symbol=m.group(1).upper())

    # /回测 策略名 AAPL
    m = re.match(r'^/回测\s+(\S+)\s+([A-Za-z]+)', text)
    if m:
        return ParsedCommand(command="backtest", symbol=m.group(2).upper(), args=m.group(1))

    # /持仓
    if text.startswith('/持仓'):
        return ParsedCommand(command="watchlist")

    # /模型 gpt-4o
    m = re.match(r'^/模型\s+(\S+)', text)
    if m:
        return ParsedCommand(command="switch_model", args=m.group(1))

    # /帮助
    if text.startswith('/帮助') or text.startswith('/help'):
        return ParsedCommand(command="help")

    # 自由对话（可能包含股票代码）
    symbols = re.findall(r'\b([A-Z]{1,5})\b', text.upper())
    symbol = symbols[0] if symbols else None
    return ParsedCommand(command="chat", symbol=symbol, args=text)
