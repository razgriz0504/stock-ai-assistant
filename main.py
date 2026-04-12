"""美股 AI 交易助手 - FastAPI 入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from config import settings
from db.models import init_db
from app.api.feishu_webhook import router as feishu_router
from app.api.health import router as health_router
from app.api.web_chat import router as chat_router
from app.api.settings import router as settings_router
from app.api.backtest_page import router as backtest_router
from app.monitor.scheduler import start_scheduler, stop_scheduler

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
    start_scheduler()
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

# 注册路由
app.include_router(health_router)
app.include_router(feishu_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(backtest_router)


@app.get("/")
async def root():
    return {
        "service": "Stock AI Trading Assistant",
        "status": "running",
        "docs": "/docs",
    }
