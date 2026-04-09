"""消息处理器 - 路由命令到对应功能模块"""
import logging
import json
import os
from datetime import datetime

from app.bot.commands import parse_command, HELP_TEXT
from app.bot.feishu_client import send_text, send_image, reply_text
from app.analysis.ai_advisor import analyze_with_ai
from app.analysis.chart_generator import generate_chart
from app.llm.client import chat, set_model, get_model, list_models, SUPPORTED_MODELS
from app.monitor.price_monitor import add_monitor_rule, remove_monitor_rules, list_user_monitors
from app.backtest.engine import run_backtest
from app.analysis.stock_analyzer import StockAnalyzer

logger = logging.getLogger(__name__)


async def handle_message(chat_id: str, message_id: str, sender_id: str, text: str):
    """处理用户消息（在后台异步执行）"""
    try:
        cmd = parse_command(text)
        logger.info(f"Command: {cmd.command}, symbol: {cmd.symbol}, from: {sender_id}")

        if cmd.command == "help":
            await send_text(chat_id, HELP_TEXT)

        elif cmd.command == "analyze":
            await send_text(chat_id, f"正在分析 {cmd.symbol}，请稍候...")
            try:
                report, ai_advice = await analyze_with_ai(cmd.symbol)
                result = f"{report}\n\n{'='*40}\nAI 分析建议 (模型: {get_model()}):\n{'='*40}\n{ai_advice}"
                await send_text(chat_id, result)
            except Exception as e:
                await send_text(chat_id, f"分析 {cmd.symbol} 失败: {e}")

        elif cmd.command == "chart":
            await send_text(chat_id, f"正在生成 {cmd.symbol} 技术图表...")
            try:
                chart_path = generate_chart(cmd.symbol)
                await send_image(chat_id, chart_path)
                # 清理临时图片
                try:
                    os.remove(chart_path)
                except OSError:
                    pass
            except Exception as e:
                await send_text(chat_id, f"生成 {cmd.symbol} 图表失败: {e}")

        elif cmd.command == "monitor":
            try:
                result = add_monitor_rule(cmd.symbol, cmd.args, sender_id, chat_id)
                await send_text(chat_id, result)
            except Exception as e:
                await send_text(chat_id, f"设置监控失败: {e}")

        elif cmd.command == "cancel_monitor":
            try:
                result = remove_monitor_rules(cmd.symbol, sender_id)
                await send_text(chat_id, result)
            except Exception as e:
                await send_text(chat_id, f"取消监控失败: {e}")

        elif cmd.command == "watchlist":
            try:
                result = list_user_monitors(sender_id)
                await send_text(chat_id, result)
            except Exception as e:
                await send_text(chat_id, f"查询监控列表失败: {e}")

        elif cmd.command == "backtest":
            await send_text(chat_id, f"正在回测 {cmd.args} 策略 ({cmd.symbol})...")
            try:
                result = run_backtest(cmd.symbol, cmd.args)
                await send_text(chat_id, result)
            except Exception as e:
                await send_text(chat_id, f"回测失败: {e}")

        elif cmd.command == "switch_model":
            actual_model = set_model(cmd.args)
            models_info = "\n".join(f"  {k} -> {v}" for k, v in SUPPORTED_MODELS.items())
            await send_text(chat_id, f"模型已切换为: {actual_model}\n\n支持的模型简写:\n{models_info}")

        elif cmd.command == "chat":
            # 自由对话模式
            system = "你是一位专业的美股交易分析助手，使用中文回答。"
            if cmd.symbol:
                system += f" 用户可能在问关于 {cmd.symbol} 的问题。"
            try:
                response = await chat(cmd.args, system_prompt=system)
                await send_text(chat_id, response)
            except Exception as e:
                await send_text(chat_id, f"AI 回复失败: {e}")

        else:
            await send_text(chat_id, f"未识别的命令。发送 /帮助 查看支持的命令列表。")

    except Exception as e:
        logger.error(f"Message handling error: {e}", exc_info=True)
        try:
            await send_text(chat_id, f"处理消息时发生错误: {e}")
        except Exception:
            logger.error("Failed to send error message to user", exc_info=True)
