"""APScheduler 定时任务管理 - 美股交易时段监控"""
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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


# ─── 周报定时任务 ───

_REPORT_JOB_MAX_RETRIES = 2  # 最大重试次数


def add_report_job(day_of_week: str = "fri", hour: int = 17, minute: int = 0):
    """添加/更新周报定时生成任务"""
    scheduler.add_job(
        _run_report_job,
        CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=ET),
        id="report_scheduled",
        replace_existing=True,
    )
    logger.info(f"Report job scheduled at {day_of_week} {hour:02d}:{minute:02d} ET")


def remove_report_job():
    """移除周报定时生成任务"""
    try:
        scheduler.remove_job("report_scheduled")
        logger.info("Report job removed")
    except Exception:
        pass


async def _run_report_job(retry_count: int = 0):
    """定时周报生成任务（含重试机制）"""
    import json
    from db.models import SessionLocal, UserPreference
    from app.report.weekly_report import generate_full_report

    logger.info(f"Scheduled report job triggered (attempt {retry_count + 1})")
    db = SessionLocal()
    try:
        # 读取 watchlist
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == "web_default"
        ).first()
        watchlist = json.loads(pref.watchlist) if pref and pref.watchlist else []

        result = await generate_full_report(db, trigger="scheduled", watchlist=watchlist)

        if "error" in result:
            # 生成失败，判断是否需要重试
            if retry_count < _REPORT_JOB_MAX_RETRIES:
                logger.warning(f"Report generation failed, retrying ({retry_count + 1}/{_REPORT_JOB_MAX_RETRIES}): {result['error']}")
                await asyncio.sleep(30)  # 等待 30s 后重试
                await _run_report_job(retry_count=retry_count + 1)
            else:
                logger.error(f"Report generation failed after {retry_count + 1} attempts: {result['error']}")
        else:
            logger.info(f"Scheduled report completed: v{result['version']}")
    except Exception as e:
        if retry_count < _REPORT_JOB_MAX_RETRIES:
            logger.warning(f"Report job error, retrying ({retry_count + 1}/{_REPORT_JOB_MAX_RETRIES}): {e}")
            await asyncio.sleep(30)
            await _run_report_job(retry_count=retry_count + 1)
        else:
            logger.error(f"Report job failed after {retry_count + 1} attempts: {e}", exc_info=True)
    finally:
        db.close()


def restore_report_schedule():
    """启动时从 DB 恢复周报定时任务配置"""
    from db.models import SessionLocal, ReportConfig
    from app.report.weekly_report import get_or_create_report_config

    db = SessionLocal()
    try:
        config = get_or_create_report_config(db)
        if config.schedule_enabled:
            add_report_job(
                day_of_week=config.schedule_day_of_week,
                hour=config.schedule_hour,
                minute=config.schedule_minute,
            )
            logger.info("Report schedule restored from DB config")
        else:
            logger.info("Report schedule is disabled in DB config")
    except Exception as e:
        logger.error(f"Failed to restore report schedule: {e}")
    finally:
        db.close()


# ─── 选股器定时任务 ───

def add_screener_job(day_of_week: str = "mon-fri", hour: int = 16, minute: int = 30):
    """添加/更新选股器定时任务"""
    scheduler.add_job(
        _run_screener_job,
        CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=ET),
        id="screener_scheduled",
        replace_existing=True,
    )
    logger.info(f"Screener job scheduled at {day_of_week} {hour:02d}:{minute:02d} ET")


def remove_screener_job():
    """移除选股器定时任务"""
    try:
        scheduler.remove_job("screener_scheduled")
        logger.info("Screener job removed")
    except Exception:
        pass


def update_screener_schedule(config):
    """根据 ScreenerConfig 更新定时任务"""
    if config.schedule_enabled:
        add_screener_job(
            day_of_week=config.schedule_day_of_week,
            hour=config.schedule_hour,
            minute=config.schedule_minute,
        )
    else:
        remove_screener_job()


async def _run_screener_job():
    """定时选股任务：从 DB 读取预设条件执行"""
    import json
    from db.models import SessionLocal, ScreenerConfig, ScreenerPreset
    from app.screener.engine import run_screener

    logger.info("Scheduled screener job triggered")
    db = SessionLocal()
    try:
        cfg = db.query(ScreenerConfig).filter_by(id=1).first()
        if not cfg or not cfg.schedule_preset_id:
            logger.warning("No screener preset configured for scheduled run")
            return

        preset = db.query(ScreenerPreset).filter_by(id=cfg.schedule_preset_id).first()
        if not preset:
            logger.warning(f"Screener preset {cfg.schedule_preset_id} not found")
            return

        filters = json.loads(preset.filters_json) if preset.filters_json else {}
        custom_code = preset.custom_code or ""

        await run_screener(
            filters_config=filters,
            custom_code=custom_code,
            trigger="scheduled",
            preset_id=preset.id,
        )
        logger.info("Scheduled screener completed")
    except Exception as e:
        logger.error(f"Scheduled screener job error: {e}", exc_info=True)
    finally:
        db.close()


def restore_screener_schedule():
    """启动时从 DB 恢复选股器定时任务配置"""
    from db.models import SessionLocal, ScreenerConfig

    db = SessionLocal()
    try:
        cfg = db.query(ScreenerConfig).filter_by(id=1).first()
        if cfg and cfg.schedule_enabled:
            add_screener_job(
                day_of_week=cfg.schedule_day_of_week,
                hour=cfg.schedule_hour,
                minute=cfg.schedule_minute,
            )
            logger.info("Screener schedule restored from DB config")
        else:
            logger.info("Screener schedule is disabled or not configured")
    except Exception as e:
        logger.error(f"Failed to restore screener schedule: {e}")
    finally:
        db.close()


# ─── X (Twitter) 舆情监控定时任务 ───

def add_x_monitor_job(interval_hours: int = 4):
    """添加/更新 X 监控定时任务（按小时间隔触发）"""
    interval_hours = max(1, int(interval_hours or 4))
    scheduler.add_job(
        _run_x_monitor_job,
        IntervalTrigger(hours=interval_hours, timezone=ET),
        id="x_monitor_scheduled",
        replace_existing=True,
    )
    logger.info(f"X monitor job scheduled every {interval_hours} hour(s)")


def remove_x_monitor_job():
    """移除 X 监控定时任务"""
    try:
        scheduler.remove_job("x_monitor_scheduled")
        logger.info("X monitor job removed")
    except Exception:
        pass


async def _run_x_monitor_job():
    """定时调用 X 监控作业"""
    from app.x_monitor.scheduler_job import run_x_monitor_job

    logger.info("Scheduled X monitor job triggered")
    try:
        result = await run_x_monitor_job(force_process=True)
        logger.info(
            "X monitor done: accounts=%s added=%s processed=%s failed=%s errors=%s",
            result.get("accounts_total"),
            result.get("tweets_added"),
            result.get("processed"),
            result.get("failed"),
            len(result.get("errors") or []),
        )
    except Exception as e:
        logger.error(f"X monitor job error: {e}", exc_info=True)


def restore_x_monitor_schedule():
    """启动时从 DB 恢复 X 监控定时配置"""
    from db.models import SessionLocal, ReportConfig

    db = SessionLocal()
    try:
        cfg = db.query(ReportConfig).filter_by(id=1).first()
        if cfg and getattr(cfg, "x_monitor_enabled", False):
            add_x_monitor_job(interval_hours=getattr(cfg, "x_monitor_interval_hours", 4))
            logger.info("X monitor schedule restored from DB config")
        else:
            logger.info("X monitor schedule is disabled in DB config")
    except Exception as e:
        logger.error(f"Failed to restore X monitor schedule: {e}")
    finally:
        db.close()


# ─── VCP 监控定时任务 ───

def add_vcp_scan_job(hour: int = 17, minute: int = 0):
    """添加/更新 VCP 扫描定时任务（美东收盘后运行）"""
    scheduler.add_job(
        _run_vcp_scan_job,
        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=ET),
        id="vcp_scan_scheduled",
        replace_existing=True,
    )
    logger.info(f"VCP scan job scheduled at {hour:02d}:{minute:02d} ET (mon-fri)")


def remove_vcp_scan_job():
    """移除 VCP 扫描定时任务"""
    try:
        scheduler.remove_job("vcp_scan_scheduled")
        logger.info("VCP scan job removed")
    except Exception:
        pass


def add_rs_daily_job(hour: int = 16, minute: int = 30):
    """添加/更新 RS Percentile 每日预计算任务"""
    scheduler.add_job(
        _run_rs_daily_job,
        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=ET),
        id="rs_daily_scheduled",
        replace_existing=True,
    )
    logger.info(f"RS daily job scheduled at {hour:02d}:{minute:02d} ET (mon-fri)")


async def _run_vcp_scan_job():
    """定时 VCP 扫描任务"""
    from app.vcp_monitor.scanner import run_vcp_scan

    logger.info("Scheduled VCP scan job triggered")
    try:
        run_id = await run_vcp_scan(trigger="scheduled")
        logger.info(f"Scheduled VCP scan completed: run_id={run_id}")
    except Exception as e:
        logger.error(f"Scheduled VCP scan job error: {e}", exc_info=True)


async def _run_rs_daily_job():
    """定时 RS Percentile 预计算任务"""
    from app.data.rs_rating import compute_rs_snapshot
    from app.screener.universe import get_universe

    logger.info("Scheduled RS daily computation triggered")
    try:
        universe = get_universe()
        result = compute_rs_snapshot(universe)
        logger.info(f"RS daily computation completed: {len(result)} stocks")
    except Exception as e:
        logger.error(f"RS daily job error: {e}", exc_info=True)


def restore_vcp_schedule():
    """启动时恢复 VCP 相关定时任务"""
    # RS 预计算 16:30 ET
    add_rs_daily_job(hour=16, minute=30)
    # VCP 扫描 17:00 ET
    add_vcp_scan_job(hour=17, minute=0)
    logger.info("VCP schedule restored (RS 16:30, scan 17:00 ET)")


# ─── 存储行业研究报告定时任务 ───

def add_storage_report_job(day_of_week: str = "mon", hour: int = 8, minute: int = 0):
    """添加/更新存储行业研究报告定时生成任务"""
    scheduler.add_job(
        _run_storage_report_job,
        CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=ET),
        id="storage_report_scheduled",
        replace_existing=True,
    )
    logger.info(f"Storage report job scheduled at {day_of_week} {hour:02d}:{minute:02d} ET")


def remove_storage_report_job():
    """移除存储行业研究报告定时生成任务"""
    try:
        scheduler.remove_job("storage_report_scheduled")
        logger.info("Storage report job removed")
    except Exception:
        pass


async def _run_storage_report_job():
    """定时生成完整存储行业研究报告"""
    import json
    from db.models import SessionLocal, StorageReportConfig
    from app.storage_report.analyzer import generate_full_report

    logger.info("Scheduled storage report job triggered")
    db = SessionLocal()
    try:
        cfg = db.query(StorageReportConfig).filter_by(id=1).first()
        cats = None
        if cfg and cfg.default_categories:
            try:
                cats = json.loads(cfg.default_categories)
            except (json.JSONDecodeError, TypeError):
                cats = None
        result = await generate_full_report(db, categories=cats, trigger="scheduled")
        if "error" in result:
            logger.error(f"Scheduled storage report failed: {result['error']}")
        else:
            logger.info(f"Scheduled storage report completed: v{result.get('version')}")
    except Exception as e:
        logger.error(f"Scheduled storage report job error: {e}", exc_info=True)
    finally:
        db.close()


def restore_storage_report_schedule():
    """启动时从 DB 恢复存储行业研究报告定时任务配置"""
    from db.models import SessionLocal, StorageReportConfig

    db = SessionLocal()
    try:
        cfg = db.query(StorageReportConfig).filter_by(id=1).first()
        if cfg and cfg.schedule_enabled:
            add_storage_report_job(
                day_of_week=cfg.schedule_day_of_week,
                hour=cfg.schedule_hour,
                minute=cfg.schedule_minute,
            )
            logger.info("Storage report schedule restored from DB config")
        else:
            logger.info("Storage report schedule is disabled or not configured")
    except Exception as e:
        logger.error(f"Failed to restore storage report schedule: {e}")
    finally:
        db.close()
