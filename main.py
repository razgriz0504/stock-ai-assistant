"""美股 AI 交易助手 - FastAPI 入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import settings
from db.models import init_db
from app.api.feishu_webhook import router as feishu_router
from app.api.health import router as health_router
from app.api.web_chat import router as chat_router
from app.api.settings import router as settings_router
from app.api.backtest_page import router as backtest_router
from app.api.watchlist_page import router as watchlist_router
from app.api.scoring_page import router as scoring_router
from app.api.report_admin_page import router as report_admin_router
from app.monitor.scheduler import start_scheduler, stop_scheduler, restore_report_schedule

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
    restore_report_schedule()
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
app.include_router(watchlist_router)
app.include_router(scoring_router)
app.include_router(report_admin_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock AI Assistant</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f1923; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }
h1 { color: #4fc3f7; font-size: 28px; margin-bottom: 6px; }
.subtitle { color: #78909c; font-size: 14px; margin-bottom: 40px; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; max-width: 640px; width: 100%; }
.card {
    background: #1a2634; border: 1px solid #2a3a4a; border-radius: 12px;
    padding: 24px; text-decoration: none; color: inherit;
    transition: border-color .2s, transform .15s;
}
.card:hover { border-color: #4fc3f7; transform: translateY(-2px); }
.card-icon { font-size: 28px; margin-bottom: 12px; }
.card-title { font-size: 17px; font-weight: 700; color: #e0e0e0; margin-bottom: 6px; }
.card-desc { font-size: 13px; color: #78909c; line-height: 1.5; }
.footer { margin-top: 40px; color: #37474f; font-size: 12px; }
@media (max-width: 500px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1>Stock AI Assistant</h1>
<p class="subtitle">US Stock AI Trading Assistant</p>

<div class="grid">
    <a class="card" href="/chat">
        <div class="card-icon">&#x1f4ac;</div>
        <div class="card-title">AI Chat</div>
        <div class="card-desc">AI stock analysis chat, ask questions about the market</div>
    </a>
    <a class="card" href="/backtest">
        <div class="card-icon">&#x1f4c8;</div>
        <div class="card-title">Strategy Backtest</div>
        <div class="card-desc">Paste Python strategy code, run backtests with charts</div>
    </a>
    <a class="card" href="/scoring">
        <div class="card-icon">&#x1f4ca;</div>
        <div class="card-title">投研周报</div>
        <div class="card-desc">Weekly market overview, sector analysis & stock scoring</div>
    </a>
    <a class="card" href="/watchlist">
        <div class="card-icon">&#x2b50;</div>
        <div class="card-title">Watchlist</div>
        <div class="card-desc">Manage your stock watchlist for scoring</div>
    </a>
    <a class="card" href="/settings">
        <div class="card-icon">&#x2699;</div>
        <div class="card-title">Settings</div>
        <div class="card-desc">Configure LLM models and API keys</div>
    </a>
    <a class="card" href="/report-admin">
        <div class="card-icon">&#x1f4cb;</div>
        <div class="card-title">周报管理</div>
        <div class="card-desc">Manage weekly reports, prompts & schedules</div>
    </a>
    <a class="card" href="/docs">
        <div class="card-icon">&#x1f4d6;</div>
        <div class="card-title">API Docs</div>
        <div class="card-desc">Swagger API documentation for developers</div>
    </a>
</div>

<div class="footer">v1.0.0</div>
</body>
</html>"""
