# 模块架构

## 数据流全景

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
│   Web 页面 (HTML in Python)  │  飞书 Bot  │  API (/docs)        │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                       FastAPI 路由层                              │
│   app/api/*.py — 每个页面一个文件，包含路由 + 内嵌前端 HTML         │
└──────┬──────────┬───────────┬──────────┬──────────┬─────────────┘
       │          │           │          │          │
       ▼          ▼           ▼          ▼          ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│  report/ ││ screener/││ backtest/││x_monitor/││ monitor/ │
│  周报引擎 ││ 选股引擎  ││ 回测引擎  ││ 舆情监控  ││ 价格监控  │
└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
     │           │           │           │           │
     └─────────┬─┴─────────┬─┴───────────┘           │
               │            │                         │
               ▼            ▼                         ▼
        ┌────────────┐┌──────────────┐      ┌──────────────┐
        │ app/llm/   ││ app/data/    │      │ APScheduler  │
        │ LLM 统一层  ││ 数据源抽象层  │      │ 定时调度      │
        └─────┬──────┘└──────┬───────┘      └──────────────┘
              │              │
              ▼              ▼
        ┌──────────┐  ┌──────────────┐
        │ LiteLLM  │  │yfinance/     │
        │ (多模型)  │  │Finnhub/Yahoo │
        └──────────┘  └──────────────┘
```

## 各模块职责

### `app/llm/client.py` — LLM 统一调用层

- **核心函数**: `chat(prompt, system_prompt, model, web_search)` — 异步调用 LLM
- **支持模型**: Gemini、GPT-4o、GPT-4o-mini、通义千问、MiniMax
- **联网搜索**: `web_search=True` 时为 Gemini 添加 `tools=[{"google_search": {}}]`
- **Grounding 引用**: 自动从响应中提取 `groundingMetadata`，在文本中插入 `[1](url)` 格式引用
- **安全设置**: Gemini 降低安全过滤（金融话题容易被误判）
- **超时**: 普通 60s，联网搜索 120s

### `app/report/weekly_report.py` — 投研周报引擎

- 详见 [WEEKLY-REPORT.md](./WEEKLY-REPORT.md)

### `app/screener/` — 选股器

- 详见 [SCREENER.md](./SCREENER.md)

### `app/x_monitor/` — X 舆情监控

- 详见 [X-MONITOR.md](./X-MONITOR.md)

### `app/data/` — 数据源抽象层

- `provider.py`: 定义 `DataProvider` 基类和 `Quote` 数据结构
- `yfinance_provider.py`: 主数据源，提供历史行情 (`get_history`)、实时报价 (`get_realtime_quote`)、基本面数据 (`get_fundamentals`)
- `finnhub_provider.py`: 备选实时数据源（Finnhub API）
- 基本面数据有 24h 缓存机制

### `app/backtest/` — 策略回测

- `engine.py`: 回测引擎，获取历史数据 → 策略生成信号 → 模拟交易 → 计算指标 → 生成报告
- `strategies.py`: 内置策略库（SMA 交叉、MACD 等）
- `sandbox.py`: 用户自定义代码沙箱执行

### `app/monitor/` — 定时任务 + 价格监控

- `scheduler.py`: APScheduler 管理（美东时区），负责：
  - 交易时段价格监控（周一~周五 9:30-16:00，每 5 分钟）
  - 周报定时生成
  - 选股器定时运行
  - X 监控定时抓取
- `price_monitor.py`: 检查 `MonitorRule` 表中的规则是否触发
- `alert_rules.py`: 告警规则逻辑

### `app/bot/` — 飞书 Bot

- `feishu_client.py`: 飞书 API 调用（发送消息、获取 token）
- `message_handler.py`: 消息处理 + 路由
- `commands.py`: `/price AAPL`、`/monitor` 等命令解析

### `app/analysis/` — 技术分析

- `stock_analyzer.py`: StockAnalyzer 类 — 获取数据、计算全套技术指标（MA/EMA/MACD/KDJ/RSI/BOLL）、生成评分和建议
- `chart_generator.py`: 用 matplotlib/mplfinance 生成 K 线图
- `ai_advisor.py`: AI 投顾对话（带上下文）

### `db/models.py` — 数据库模型

- ORM 使用 SQLAlchemy，数据库为 SQLite 单文件
- 核心表: `weekly_reports`、`report_config`、`screener_runs`、`screener_results`、`x_accounts`、`x_tweets`、`monitor_rules`、`backtest_records`
- **自动迁移**: `_migrate_missing_columns()` 函数在 `init_db()` 时自动检测并 ALTER TABLE 添加新列

## 前端渲染

所有 Web 页面的前端 HTML **直接内嵌在 Python 路由文件中**（不使用模板引擎）：

- 使用 `marked.js` 渲染 Markdown 输出
- 使用 `KaTeX` 渲染 LaTeX 公式
- 暗色主题风格（#0f1923 背景）
- 响应式布局

## API 路由总表

| 路由文件 | 挂载路径 | 功能 |
|---------|---------|------|
| `report_api.py` | `/scoring` | 周报查看（公开页面） |
| `report_admin_api.py` | `/report-admin` | 周报管理（生成/配置/历史） |
| `screener_api.py` | `/screener` | 选股器 |
| `x_monitor_api.py` | `/x-monitor` | X 舆情监控 |
| `backtest_api.py` | `/backtest` | 策略回测 |
| `watchlist_api.py` | `/watchlist` | 自选股管理 |
| `web_chat.py` | `/chat` | AI 对话 |
| `settings.py` | `/settings` | 系统设置（模型切换等） |
| `health.py` | `/health` | 健康检查 |
| `feishu_webhook.py` | `/feishu/webhook` | 飞书事件回调 |
