import os
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
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


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
