"""美股 AI 交易助手 - FastAPI 入口"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.models import init_db, SessionLocal, get_or_create_x_accounts
from app.api.feishu_webhook import router as feishu_router
from app.api.health import router as health_router
from app.api.web_chat import router as chat_router
from app.api.settings import router as settings_router
from app.api.backtest_api import router as backtest_router
from app.api.watchlist_api import router as watchlist_router
from app.api.report_api import router as scoring_router
from app.api.report_admin_api import router as report_admin_router
from app.api.screener_api import router as screener_router
from app.api.x_monitor_api import router as x_monitor_router
from app.api.sector_strength_api import router as sector_strength_router
from app.api.dashboard_api import router as dashboard_router
from app.api.vcp_monitor_api import router as vcp_monitor_router
from app.api.storage_report_api import router as storage_report_router
from app.api.futu_api import router as futu_router
from app.monitor.scheduler import (
    start_scheduler, stop_scheduler, restore_report_schedule,
    restore_screener_schedule, restore_x_monitor_schedule,
    restore_vcp_schedule, restore_storage_report_schedule,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting Stock AI Assistant...")
    init_db()
    logger.info("Database initialized")
    # 种子默认 X 账号
    try:
        _seed_db = SessionLocal()
        try:
            seeded = get_or_create_x_accounts(_seed_db)
            if seeded:
                logger.info(f"Seeded {len(seeded)} default X accounts")
        finally:
            _seed_db.close()
    except Exception as e:
        logger.warning(f"X accounts seeding skipped: {e}")
    start_scheduler()
    restore_report_schedule()
    restore_screener_schedule()
    restore_x_monitor_schedule()
    restore_vcp_schedule()
    restore_storage_report_schedule()
    logger.info("Scheduler started")
    logger.info(f"Default LLM: {settings.default_llm}")

    yield

    # 关闭时
    stop_scheduler()
    logger.info("Stock AI Assistant stopped")


app = FastAPI(
    title="Stock AI Trading Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 仅在开发/本地环境启用，生产环境同域部署(nginx 代理)无需
if os.getenv("ENABLE_DEV_CORS", "0") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 注册路由
app.include_router(health_router)
app.include_router(feishu_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(backtest_router)
app.include_router(watchlist_router)
app.include_router(scoring_router)
app.include_router(report_admin_router)
app.include_router(screener_router)
app.include_router(x_monitor_router)
app.include_router(sector_strength_router)
app.include_router(dashboard_router)
app.include_router(vcp_monitor_router)
app.include_router(storage_report_router)
app.include_router(futu_router)


@app.get("/")
async def root():
    """后端 API 服务心跳 - 生产环境下 nginx 将 / 路由到 SPA 静态资源,此路由仅在直连 8000 端口时被命中。"""
    return {
        "service": "Stock AI Assistant API",
        "version": "1.0.0",
        "docs": "/docs",
        "frontend": "请访问部署域名或本地 http://localhost:5173 (npm run dev)",
    }
