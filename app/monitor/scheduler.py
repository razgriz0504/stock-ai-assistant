"""APScheduler 定时任务管理 - 美股交易时段监控"""
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.monitor.price_monitor import check_all_monitors
from app.bot.feishu_client import send_text

logger = logging.getLogger(__name__)

# 美东时区（自动处理夏令时/冬令时）
ET = pytz.timezone("America/New_York")

scheduler = AsyncIOScheduler(timezone=ET)

# 存储 chat_id 用于推送（单用户场景，启动时从 DB 获取）
_default_chat_id: str = ""


def set_default_chat_id(chat_id: str):
    """设置默认推送的 chat_id（首次收到消息时自动记录）"""
    global _default_chat_id
    _default_chat_id = chat_id


async def _check_monitors_job():
    """定时检查监控规则，触发则推送"""
    try:
        triggered = check_all_monitors()
        for item in triggered:
            msg = (
                f"监控预警触发!\n"
                f"股票: {item['symbol']}\n"
                f"条件: {item['description']}\n"
                f"当前价格: ${item['current_price']:.2f}"
            )
            # 尝试推送到用户（需要 chat_id，这里用 _default_chat_id）
            if _default_chat_id:
                await send_text(_default_chat_id, msg)
            logger.info(f"Monitor triggered: {item}")
    except Exception as e:
        logger.error(f"Monitor job error: {e}", exc_info=True)


def start_scheduler():
    """启动定时任务"""
    # 美股交易时段 (美东 09:30 - 16:00)，每5分钟检查一次
    scheduler.add_job(
        _check_monitors_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/5",
            timezone=ET,
        ),
        id="monitor_trading_hours",
        replace_existing=True,
    )
    # 16:00 最后检查一次
    scheduler.add_job(
        _check_monitors_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour=16,
            minute=0,
            timezone=ET,
        ),
        id="monitor_market_close",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started (timezone: America/New_York)")


def stop_scheduler():
    """停止定时任务"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


# ─── 打分定时任务 ───

def add_scoring_job(hour: int = 16, minute: int = 30):
    """添加/更新打分定时任务，美东时间每个交易日执行"""
    scheduler.add_job(
        _run_scoring_job,
        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=ET),
        id="scoring_scheduled",
        replace_existing=True,
    )
    logger.info(f"Scoring job scheduled at {hour:02d}:{minute:02d} ET (mon-fri)")


def remove_scoring_job():
    """移除打分定时任务"""
    try:
        scheduler.remove_job("scoring_scheduled")
        logger.info("Scoring job removed")
    except Exception:
        pass


async def _run_scoring_job():
    """定时打分任务：从 DB 读取最新策略代码 + watchlist，执行打分"""
    import json
    from db.models import SessionLocal, ScoringRun, UserPreference

    logger.info("Scheduled scoring job triggered")
    db = SessionLocal()
    try:
        # 读取最近一次的策略代码
        last_run = db.query(ScoringRun).order_by(ScoringRun.id.desc()).first()
        if not last_run or not last_run.code:
            logger.warning("No previous scoring code found, skipping scheduled run")
            return

        # 读取 watchlist
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == "web_default"
        ).first()
        symbols = json.loads(pref.watchlist) if pref and pref.watchlist else []
        if not symbols:
            logger.warning("Watchlist empty, skipping scheduled run")
            return

        # 执行打分
        from app.scoring.scorer import run_scoring
        result = run_scoring(last_run.code, symbols,
                           period=last_run.period or "1y",
                           trigger="scheduled")
        if result["success"]:
            logger.info(f"Scheduled scoring completed: v{result['version']}, {len(result['results'])} stocks")
        else:
            logger.error(f"Scheduled scoring failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"Scheduled scoring job error: {e}", exc_info=True)
    finally:
        db.close()
