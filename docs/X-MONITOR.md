# X (Twitter) 舆情监控

## 概述

监控一组 Twitter 关键账号（美联储、分析师、CEO、财经媒体等），定时抓取推文，用 AI 进行翻译、情感分析和市场影响评估。结果整合进投研周报的"舆情综述"section。

## 系统架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  scheduler   │────▶│   client.py  │────▶│ X API v2     │
│  定时触发     │     │  HTTP 客户端  │     │ (Twitter)    │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │ 推文写入 DB
                            ▼
                     ┌──────────────┐
                     │  x_tweets 表  │
                     │ (processed=F) │
                     └──────┬───────┘
                            │ AI 批量处理
                            ▼
                     ┌──────────────┐     ┌──────────────┐
                     │ processor.py │────▶│ LLM (Gemini) │
                     │  AI 处理器    │     │ 翻译+分析     │
                     └──────┬───────┘     └──────────────┘
                            │ 更新 DB
                            ▼
                     ┌──────────────┐
                     │  x_tweets 表  │
                     │ (processed=T) │
                     └──────────────┘
                            │ 周报聚合
                            ▼
                     ┌──────────────────────────┐
                     │ weekly_report.py          │
                     │ fetch_x_tweets_data()     │
                     │ generate_ai_x_monitor()   │
                     └──────────────────────────┘
```

## 三个核心模块

### 1. `client.py` — X API v2 HTTP 客户端

- 直接使用 `requests` 调用 X API v2 端点
- Bearer Token 认证（存在 `report_config.x_api_bearer_token`）
- 支持: 获取用户时间线推文、用户 ID 查询
- 增量抓取: 每个账号维护 `last_tweet_id` 作为 since_id 游标
- 429 限流处理: 自动等待 + 重试

### 2. `processor.py` — AI 推文处理器

- **输入**: 英文推文原文
- **输出**: 结构化 JSON（中文翻译 + 要点 + 情感 + 影响标的 + 市场影响评述）
- **LLM prompt**: 要求输出严格 JSON 格式
- **容错**: `_extract_json()` 处理 LLM 输出中的 markdown 代码块和不规范 JSON
- **并发控制**: `asyncio.Semaphore` 限制并发数（默认 3）
- **批量处理**: `process_pending_tweets()` 处理所有 `processed=False` 的推文

### 3. `scheduler_job.py` — 定时抓取任务

- 定时（每 N 小时，默认 4h）触发
- 遍历所有 `enabled=True` 的 X 账号
- 增量拉取新推文 → 写入 `x_tweets` 表
- 触发 AI 处理

## 数据库表

### `x_accounts` — 监控账号

- `username`: Twitter 用户名（不带 @）
- `category`: 分类（fed/macro/analyst/ceo/media）
- `enabled`: 是否启用
- `last_tweet_id`: 增量游标

### `x_tweets` — 推文存档

- `tweet_id`: X 平台推文 ID
- `text`: 英文原文
- `text_zh`: 中文翻译（AI 生成）
- `key_points`: JSON 数组（中文要点）
- `sentiment`: bullish / bearish / neutral
- `impact_assets`: JSON 数组（受影响标的，如 ["SPY", "TLT"]）
- `market_impact`: 中文市场影响评述
- `processed`: 是否已 AI 处理

## 默认监控账号

| 账号 | 分类 | 身份 |
|------|------|------|
| @federalreserve | fed | 美联储官方 |
| @ecb | fed | 欧央行 |
| @nouriel | macro | Nouriel Roubini（经济学家）|
| @elerianm | macro | El-Erian（PIMCO 前 CIO）|
| @LizAnnSonders | analyst | 嘉信理财首席策略师 |
| @elonmusk | ceo | Elon Musk |
| @CathieDWood | ceo | ARK Invest CEO |
| @jimcramer | analyst | CNBC Mad Money |
| @business | media | Bloomberg |
| @CNBC | media | CNBC |

## 周报整合

- `fetch_x_tweets_data(db, days=7)`: 聚合过去 7 天推文，按账号分组，统计情感分布、高频标的、高互动推文
- `generate_ai_x_monitor_summary(x_data)`: 将聚合数据传给 LLM，生成舆情综述（不联网，因为数据已经够了）
- 输出结构: 整体舆情温度 → 关键议题 → 代表性发言 → 被关注标的 → 风险提示

## 配置项（report_config 表）

- `x_api_bearer_token`: X API 认证 token
- `x_monitor_enabled`: 是否启用定时抓取
- `x_monitor_interval_hours`: 抓取间隔（小时）
- `default_x_tweet_system_prompt`: 单条推文处理 prompt
- `default_x_monitor_system_prompt`: 周报舆情综述 prompt

## 前端页面

- URL: `/x-monitor`
- 功能: 查看已处理推文、账号管理、手动触发抓取、配置 API token
