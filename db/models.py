import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

# 数据库文件放在项目根目录的 db/ 下，使用绝对路径避免工作目录问题
_BASE_DIR = Path(__file__).resolve().parent
_DB_PATH = _BASE_DIR / "stock_ai.db"
DATABASE_URL = f"sqlite:///{_DB_PATH}?check_same_thread=False"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class MonitorRule(Base):
    """价格监控规则"""
    __tablename__ = "monitor_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    condition_type = Column(String(20), nullable=False)  # price_above, price_below, change_pct
    threshold = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    feishu_user_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    triggered_at = Column(DateTime, nullable=True)
    description = Column(String(200), default="")


class BacktestRecord(Base):
    """回测记录"""
    __tablename__ = "backtest_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    strategy_name = Column(String(50), nullable=False)
    period = Column(String(20), nullable=False)
    total_return = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    win_rate = Column(Float, nullable=True)
    report_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    feishu_user_id = Column(String(100), default="")


class UserPreference(Base):
    """用户偏好设置"""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feishu_user_id = Column(String(100), nullable=False, unique=True)
    default_model = Column(String(50), default="")
    watchlist = Column(Text, default="")  # JSON: ["AAPL","TSLA"]
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ScoringRun(Base):
    """打分版本记录"""
    __tablename__ = "scoring_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False)
    code = Column(Text, nullable=False)
    period = Column(String(20), default="1y")
    trigger = Column(String(20), default="manual")  # "manual" / "scheduled"
    stock_count = Column(Integer, default=0)
    status = Column(String(20), default="running")  # "running", "completed", "failed"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScoringResult(Base):
    """单只股票的打分结果"""
    __tablename__ = "scoring_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    score = Column(Float, nullable=True)
    rating = Column(String(5), default="")
    price = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    details_json = Column(Text, default="")  # JSON: {"MACD": {...}, ...}
    error = Column(Text, default="")


class WeeklyReport(Base):
    """投研周报 - 版本化存储"""
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, index=True)
    report_date = Column(DateTime, index=True)
    status = Column(String(20), default="running")   # running / completed / failed
    trigger = Column(String(20), default="manual")    # manual / scheduled
    model_name = Column(String(100), default="")       # 生成时使用的 LLM 模型
    # --- 数据（JSON 存储） ---
    index_data = Column(Text, default="")              # JSON: 三大指数数据
    sector_data = Column(Text, default="")             # JSON: 行业ETF表现
    watchlist_scores = Column(Text, default="")         # JSON: watchlist评分结果
    hot_stock_scores = Column(Text, default="")         # JSON: 热门股评分结果
    # --- AI 分析 ---
    ai_market_summary = Column(Text, default="")        # AI大盘综述
    ai_capital_summary = Column(Text, default="")       # AI资金面分析
    ai_sector_summary = Column(Text, default="")        # AI行业分析
    ai_stocks_summary = Column(Text, default="")        # 预留：个股AI综合分析
    # --- Prompt 审计 ---
    market_system_prompt = Column(Text, default="")     # 生成时使用的市场分析 prompt
    capital_system_prompt = Column(Text, default="")    # 生成时使用的资金面分析 prompt
    sector_system_prompt = Column(Text, default="")     # 生成时使用的行业分析 prompt
    stocks_system_prompt = Column(Text, default="")     # 预留：个股分析 prompt
    # --- 元数据 ---
    watchlist_used = Column(Text, default="")           # JSON: 生成时使用的 watchlist
    error_message = Column(Text, default="")            # 失败时的错误信息
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ReportConfig(Base):
    """报告配置（单例表，id=1）"""
    __tablename__ = "report_config"

    id = Column(Integer, primary_key=True, default=1)
    # --- 定时生成 ---
    schedule_enabled = Column(Boolean, default=False)
    schedule_frequency = Column(String(20), default="weekly")  # weekly / daily
    schedule_day_of_week = Column(String(10), default="fri")
    schedule_hour = Column(Integer, default=17)                # ET 时区
    schedule_minute = Column(Integer, default=0)
    # --- 默认 Prompt ---
    default_market_system_prompt = Column(Text, default="")
    default_capital_system_prompt = Column(Text, default="")
    default_sector_system_prompt = Column(Text, default="")
    default_stocks_system_prompt = Column(Text, default="")
    # --- 元数据 ---
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


def init_db():
    """初始化数据库，创建所有表 + 自动迁移缺失列"""
    Base.metadata.create_all(bind=engine)
    _migrate_missing_columns()


def _migrate_missing_columns():
    """检测并添加缺失的列（SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS）"""
    # 需要迁移的列: (表名, 列名, 列类型 SQL)
    migrations = [
        ("report_config", "default_capital_system_prompt", "TEXT DEFAULT ''"),
        ("weekly_reports", "ai_capital_summary", "TEXT DEFAULT ''"),
        ("weekly_reports", "capital_system_prompt", "TEXT DEFAULT ''"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            # PRAGMA table_info 获取现有列名
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            existing_cols = {row[1] for row in result}
            if column not in existing_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger = logging.getLogger(__name__)
                logger.info(f"Migration: added column {table}.{column}")


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
