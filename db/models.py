import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, text
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
    yield_curve_data = Column(Text, default="")         # JSON: 国债收益率曲线数据
    x_tweets_data = Column(Text, default="")            # JSON: X 关键账号推文快照
    # --- AI 分析 ---
    ai_market_summary = Column(Text, default="")        # AI大盘综述
    ai_capital_summary = Column(Text, default="")       # AI资金面分析
    ai_geopolitics_summary = Column(Text, default="")   # AI国际局势分析
    ai_sector_summary = Column(Text, default="")        # AI行业分析
    ai_stocks_summary = Column(Text, default="")        # 预留：个股AI综合分析
    ai_yield_curve_summary = Column(Text, default="")   # AI国债收益率曲线分析
    ai_x_monitor_summary = Column(Text, default="")     # AI X 舆情综述
    # --- Prompt 审计 ---
    market_system_prompt = Column(Text, default="")     # 生成时使用的市场分析 prompt
    capital_system_prompt = Column(Text, default="")    # 生成时使用的资金面分析 prompt
    geopolitics_system_prompt = Column(Text, default="") # 生成时使用的国际局势分析 prompt
    sector_system_prompt = Column(Text, default="")     # 生成时使用的行业分析 prompt
    stocks_system_prompt = Column(Text, default="")     # 预留：个股分析 prompt
    yield_curve_system_prompt = Column(Text, default="") # 生成时使用的国债收益率曲线分析 prompt
    x_monitor_system_prompt = Column(Text, default="")  # 生成时使用的 X 舆情综述 prompt
    sector_strength_system_prompt = Column(Text, default="")  # 生成时使用的板块强度分析 prompt
    # --- 增强板块数据 ---
    enhanced_sector_data = Column(Text, default="")      # JSON: 增强板块强度数据快照
    ai_sector_strength_summary = Column(Text, default="") # AI板块轮动分析
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
    default_geopolitics_system_prompt = Column(Text, default="")
    default_sector_system_prompt = Column(Text, default="")
    default_stocks_system_prompt = Column(Text, default="")
    default_yield_curve_system_prompt = Column(Text, default="")
    # --- X 监控配置 ---
    x_api_bearer_token = Column(Text, default="")           # X API v2 Bearer Token
    x_monitor_enabled = Column(Boolean, default=False)
    x_monitor_interval_hours = Column(Integer, default=4)
    default_x_tweet_system_prompt = Column(Text, default="")     # 单条推文处理 prompt
    default_x_monitor_system_prompt = Column(Text, default="")   # 周报 X 综述 prompt
    # --- 板块强度 ---
    default_sector_strength_system_prompt = Column(Text, default="")  # 增强板块分析 prompt
    # --- 元数据 ---
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# Screener 选股器相关表
# ═══════════════════════════════════════════════════════════════

class ScreenerPreset(Base):
    """选股器预设条件"""
    __tablename__ = "screener_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    filters_json = Column(Text, default="{}")       # JSON: 完整筛选条件配置
    custom_code = Column(Text, default="")           # 用户自定义 Python 筛选代码
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ScreenerRun(Base):
    """选股器执行记录"""
    __tablename__ = "screener_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False)
    preset_id = Column(Integer, nullable=True)       # 使用的预设 ID
    filters_json = Column(Text, default="{}")        # 本次使用的筛选条件快照
    custom_code = Column(Text, default="")           # 本次使用的自定义代码快照
    trigger = Column(String(20), default="manual")   # "manual" / "scheduled"
    status = Column(String(20), default="running")   # "running" / "completed" / "failed"
    total_stocks = Column(Integer, default=0)        # 扫描股票总数
    passed_stocks = Column(Integer, default=0)       # 通过筛选的股票数
    progress_pct = Column(Integer, default=0)        # 进度 0-100
    error_message = Column(Text, default="")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class ScreenerResult(Base):
    """选股器单只股票结果"""
    __tablename__ = "screener_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    passed = Column(Boolean, default=False)
    score = Column(Float, nullable=True)              # 技术评分 1-5
    rating = Column(String(5), default="")            # AA/A/B/C/D
    price = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    filter_details_json = Column(Text, default="{}")  # 各筛选条件通过/失败详情
    indicators_json = Column(Text, default="{}")      # 关键指标值快照


class ScreenerConfig(Base):
    """选股器定时配置（单例表，id=1）"""
    __tablename__ = "screener_config"

    id = Column(Integer, primary_key=True, default=1)
    schedule_enabled = Column(Boolean, default=False)
    schedule_frequency = Column(String(20), default="daily")  # daily / weekly
    schedule_day_of_week = Column(String(10), default="mon-fri")
    schedule_hour = Column(Integer, default=16)                # ET 16:30 收盘后
    schedule_minute = Column(Integer, default=30)
    schedule_preset_id = Column(Integer, nullable=True)        # 定时运行的预设 ID
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# X (Twitter) 舆情监控相关表
# ═══════════════════════════════════════════════════════════════

class XAccount(Base):
    """X 监控账号"""
    __tablename__ = "x_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)  # 不带 @
    x_user_id = Column(String(64), default="")                              # X 平台 numeric id
    display_name = Column(String(128), default="")
    category = Column(String(32), default="")           # macro / fed / analyst / ceo / media
    enabled = Column(Boolean, default=True)
    last_tweet_id = Column(String(64), default="")      # since_id 增量游标
    last_fetched_at = Column(DateTime, nullable=True)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class XTweet(Base):
    """X 推文存档"""
    __tablename__ = "x_tweets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tweet_id = Column(String(64), unique=True, index=True, nullable=False)
    account_id = Column(Integer, ForeignKey("x_accounts.id"), index=True)
    username = Column(String(64), index=True)
    text = Column(Text)                                  # 原文
    text_zh = Column(Text, default="")                   # 中文翻译
    key_points = Column(Text, default="[]")              # JSON list: ["要点1", "要点2"]
    sentiment = Column(String(16), default="")           # bullish / bearish / neutral
    impact_assets = Column(Text, default="[]")           # JSON list: ["SPY", "TLT"]
    market_impact = Column(Text, default="")             # 市场影响评述
    metrics = Column(Text, default="{}")                 # JSON: like/retweet/reply 计数
    created_at_x = Column(DateTime, index=True)          # X 上发布时间（UTC）
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed = Column(Boolean, default=False, index=True)
    processing_error = Column(Text, default="")


# ═══════════════════════════════════════════════════════════════
# 存储行业研究报告相关表（DRAM/NAND/HBM/SSD/HDD）
# ═══════════════════════════════════════════════════════════════

class StorageReport(Base):
    """存储行业研究报告 - 版本化存储"""
    __tablename__ = "storage_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, index=True)
    report_date = Column(DateTime, index=True)
    status = Column(String(20), default="running")     # running / completed / failed
    trigger = Column(String(20), default="manual")      # manual / scheduled
    model_name = Column(String(100), default="")
    categories = Column(Text, default="[]")             # JSON: 本次品类
    time_range = Column(String(40), default="")
    # --- 六大 section 结果（Text 存 markdown 或 JSON）---
    metric_data = Column(Text, default="")
    prosperity_data = Column(Text, default="")
    price_trend_data = Column(Text, default="")
    supply_demand_data = Column(Text, default="")
    vendor_data = Column(Text, default="")
    anomaly_data = Column(Text, default="")
    # --- Prompt 审计快照 ---
    prosperity_system_prompt = Column(Text, default="")
    price_trend_system_prompt = Column(Text, default="")
    supply_demand_system_prompt = Column(Text, default="")
    vendor_system_prompt = Column(Text, default="")
    anomaly_system_prompt = Column(Text, default="")
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class StorageReportConfig(Base):
    """存储行业研究报告配置（单例表，id=1）"""
    __tablename__ = "storage_report_config"

    id = Column(Integer, primary_key=True, default=1)
    # --- 定时生成 ---
    schedule_enabled = Column(Boolean, default=False)
    schedule_day_of_week = Column(String(10), default="mon")
    schedule_hour = Column(Integer, default=8)                  # ET 时区
    schedule_minute = Column(Integer, default=0)
    # --- 默认参数 ---
    default_categories = Column(Text, default='["DRAM","NAND","HBM"]')
    # --- 默认 Prompt ---
    default_metric_system_prompt = Column(Text, default="")
    default_prosperity_system_prompt = Column(Text, default="")
    default_price_trend_system_prompt = Column(Text, default="")
    default_supply_demand_system_prompt = Column(Text, default="")
    default_vendor_system_prompt = Column(Text, default="")
    default_anomaly_system_prompt = Column(Text, default="")
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
        ("report_config", "default_geopolitics_system_prompt", "TEXT DEFAULT ''"),
        ("weekly_reports", "ai_geopolitics_summary", "TEXT DEFAULT ''"),
        ("weekly_reports", "geopolitics_system_prompt", "TEXT DEFAULT ''"),
        # 国债收益率曲线相关迁移
        ("weekly_reports", "yield_curve_data", "TEXT DEFAULT ''"),
        ("weekly_reports", "ai_yield_curve_summary", "TEXT DEFAULT ''"),
        ("weekly_reports", "yield_curve_system_prompt", "TEXT DEFAULT ''"),
        ("report_config", "default_yield_curve_system_prompt", "TEXT DEFAULT ''"),
        # X 舆情监控相关迁移
        ("weekly_reports", "x_tweets_data", "TEXT DEFAULT ''"),
        ("weekly_reports", "ai_x_monitor_summary", "TEXT DEFAULT ''"),
        ("weekly_reports", "x_monitor_system_prompt", "TEXT DEFAULT ''"),
        ("report_config", "x_api_bearer_token", "TEXT DEFAULT ''"),
        ("report_config", "x_monitor_enabled", "INTEGER DEFAULT 0"),
        ("report_config", "x_monitor_interval_hours", "INTEGER DEFAULT 4"),
        ("report_config", "default_x_tweet_system_prompt", "TEXT DEFAULT ''"),
        ("report_config", "default_x_monitor_system_prompt", "TEXT DEFAULT ''"),
        # 板块强度雷达相关迁移
        ("weekly_reports", "enhanced_sector_data", "TEXT DEFAULT ''"),
        ("weekly_reports", "ai_sector_strength_summary", "TEXT DEFAULT ''"),
        ("weekly_reports", "sector_strength_system_prompt", "TEXT DEFAULT ''"),
        ("report_config", "default_sector_strength_system_prompt", "TEXT DEFAULT ''"),
        # VCP 监控：扫描时刻最新收盘价（用于计算距 Pivot 百分比）
        ("vcp_scan_results", "last_close", "REAL DEFAULT NULL"),
        # VCP 监控：拒绝原因（status=rejected_vcp 时记录具体原因标记）
        ("vcp_scan_results", "reject_reason", "TEXT DEFAULT NULL"),
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


# ═══════════════════════════════════════════════════════════════
# VCP (Volatility Contraction Pattern) 监控相关表
# ═══════════════════════════════════════════════════════════════

class VcpWatchlist(Base):
    """VCP 监控标的列表"""
    __tablename__ = "vcp_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    source = Column(String(20), default="manual")       # "auto" / "manual"
    auto_seeded = Column(Boolean, default=False)         # 是否由 SEPA 自动种子加入
    enabled = Column(Boolean, default=True)
    note = Column(String(200), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_triggered_at = Column(DateTime, nullable=True)  # 最后一次触发信号的时间


class VcpScanRun(Base):
    """VCP 扫描批次记录"""
    __tablename__ = "vcp_scan_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger = Column(String(20), default="manual")       # "manual" / "scheduled"
    status = Column(String(20), default="running")       # "running" / "completed" / "failed"
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    total = Column(Integer, default=0)                   # 扫描总数
    detected = Column(Integer, default=0)                # 检测到 VCP 形态的数量
    error_message = Column(Text, default="")


class VcpScanResult(Base):
    """VCP 单只股票扫描结果"""
    __tablename__ = "vcp_scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    status = Column(String(20), default="forming")       # forming/breakout/extended/failed/rejected_vcp
    score = Column(Integer, default=0)                   # 0-100 质量评分
    pivot_price = Column(Float, nullable=True)
    last_close = Column(Float, nullable=True)            # 扫描时刻最新收盘价（计算 distance_pct）
    contractions_json = Column(Text, default="[]")       # JSON: 收缩序列坐标
    volume_dry_ratio = Column(Float, nullable=True)      # 量能干枯比
    rs_percentile = Column(Float, nullable=True)
    reject_reason = Column(Text, nullable=True)          # status=rejected_vcp 时的拒绝原因标记
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VcpAlert(Base):
    """VCP 告警记录"""
    __tablename__ = "vcp_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, index=True)
    alert_type = Column(String(20), default="breakout")  # "breakout"
    pivot_price = Column(Float, nullable=True)
    breakout_price = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)          # 突破时量比
    prior_failed = Column(Boolean, default=False)        # 本次前是否经历过 failed
    sent_feishu = Column(Boolean, default=False)
    alerted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════
# 默认 X 监控账号种子
# ═══════════════════════════════════════════════════════════════

DEFAULT_X_ACCOUNTS = [
    # 宏观 / 央行
    {"username": "federalreserve", "display_name": "Federal Reserve", "category": "fed"},
    {"username": "ecb", "display_name": "European Central Bank", "category": "fed"},
    {"username": "nouriel", "display_name": "Nouriel Roubini", "category": "macro"},
    {"username": "elerianm", "display_name": "Mohamed A. El-Erian", "category": "macro"},
    {"username": "LizAnnSonders", "display_name": "Liz Ann Sonders", "category": "analyst"},
    {"username": "SteveLiesman", "display_name": "Steve Liesman", "category": "analyst"},
    # 市场 / 媒体 / CEO
    {"username": "elonmusk", "display_name": "Elon Musk", "category": "ceo"},
    {"username": "CathieDWood", "display_name": "Cathie Wood", "category": "ceo"},
    {"username": "jimcramer", "display_name": "Jim Cramer", "category": "analyst"},
    {"username": "business", "display_name": "Bloomberg Business", "category": "media"},
    {"username": "CNBC", "display_name": "CNBC", "category": "media"},
]


def get_or_create_x_accounts(db):
    """初次启动时种子默认 X 账号；返回当前所有账号"""
    existing = {a.username.lower() for a in db.query(XAccount).all()}
    added = 0
    for spec in DEFAULT_X_ACCOUNTS:
        if spec["username"].lower() in existing:
            continue
        db.add(XAccount(
            username=spec["username"],
            display_name=spec["display_name"],
            category=spec["category"],
            enabled=True,
        ))
        added += 1
    if added:
        db.commit()
        logger = logging.getLogger(__name__)
        logger.info(f"Seeded {added} default X accounts")
    return db.query(XAccount).all()
