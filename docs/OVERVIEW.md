# Stock AI Assistant - 项目总览

## 这是什么

一个**美股 AI 交易助手**，提供投研周报、选股筛选、策略回测、X 舆情监控等功能。用户通过 Web 页面或飞书 Bot 交互，后端用 AI（主要是 Gemini）生成分析内容。

## 核心能力

| 功能模块 | 做什么 | 入口 URL |
|---------|--------|----------|
| 投研周报 | 每周自动/手动生成市场分析报告（7个 section） | `/scoring` |
| 周报管理 | 配置 prompt、定时生成、查看历史 | `/report-admin` |
| Stock Screener | 批量扫描 S&P500 + Nasdaq100，用技术/基本面过滤器筛股 | `/screener` |
| 策略回测 | 粘贴 Python 策略代码，运行回测并生成收益曲线 | `/backtest` |
| X 舆情监控 | 跟踪 Twitter 关键账号，AI 翻译 + 情感分析 | `/x-monitor` |
| AI Chat | 多模型对话，股票分析问答 | `/chat` |
| 自选股 | 管理 watchlist，用于周报评分 | `/watchlist` |
| 价格监控 | 交易时段每 5 分钟检查价格条件，触发飞书推送 | 后台自动 |

## 技术栈

- **后端框架**: FastAPI + Uvicorn
- **LLM 调用**: LiteLLM 统一接口（支持 Gemini、GPT-4o、通义千问、MiniMax）
- **数据源**: yfinance（历史行情）、Finnhub（备选实时数据）
- **数据库**: SQLite + SQLAlchemy ORM（单文件，存在 `db/stock_ai.db`）
- **定时任务**: APScheduler（AsyncIO 模式，美东时区）
- **即时通讯**: 飞书 Bot Webhook
- **前端**: 纯 HTML 内嵌在 Python 文件中（marked.js 渲染 Markdown，KaTeX 渲染 LaTeX）

## 部署方式

- 运行在 Linux 服务器上
- 启动命令: `uvicorn main:app --host 0.0.0.0 --port 8000`
- 配置通过 `.env` 文件（参考 `.env.example`）
- 数据库自动初始化 + 自动迁移缺失列
- 账号体系注入：首次启动会根据 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 自动播种首个 admin；详见 [docs/ACCOUNTS.md](./ACCOUNTS.md)

## 默认 LLM

当前默认模型: `gemini/gemini-3.1-pro-preview`

Gemini 模型特殊配置：
- 启用 Google Search grounding（联网搜索）：`tools=[{"google_search": {}}]`
- 降低安全过滤阈值（避免金融话题被误拦截）
- 联网搜索模式超时 120s（普通 60s）

## 目录结构速览

```
stock-ai-assistant/
├── main.py              # FastAPI 入口，注册所有路由
├── config.py            # 环境变量配置（.env）
├── requirements.txt     # Python 依赖
├── db/models.py         # 所有 ORM 模型 + 自动迁移逻辑
├── app/
│   ├── llm/client.py    # LLM 统一调用（含 grounding 引用处理）
│   ├── report/          # 投研周报生成引擎
│   ├── screener/        # 选股器（过滤器 + 引擎）
│   ├── x_monitor/       # X 舆情监控
│   ├── backtest/        # 策略回测引擎
│   ├── data/            # 数据源抽象层
│   ├── analysis/        # 技术分析 + AI 顾问
│   ├── monitor/         # 价格监控 + 调度器
│   ├── bot/             # 飞书 Bot
│   └── api/             # Web 页面路由（含前端 HTML）
└── scripts/             # 部署脚本
```
