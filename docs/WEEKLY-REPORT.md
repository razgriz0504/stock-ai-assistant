# 投研周报 - 业务逻辑

## 概述

投研周报是本项目最核心的功能。每周生成一份包含 7 个 section 的分析报告，存储在 `weekly_reports` 表中，通过 `/scoring` 页面展示。

## 报告结构（7 个 Section）

| 序号 | Section | 数据来源 | AI 分析方式 |
|------|---------|---------|------------|
| 01 | 大盘综述 | yfinance 获取三大指数数据 | 系统数据 + AI 分析 + 联网搜索 |
| 02 | 资金面分析 | 无系统数据 | 纯 LLM 联网搜索输出 |
| 03 | 国际局势 | 无系统数据 | 纯 LLM 联网搜索输出 |
| 04 | 国债收益率曲线 | yfinance 获取国债收益率 | 系统数据 + AI 分析 + 联网搜索 |
| 05 | 行业板块 | yfinance 获取 11 个行业 ETF | 系统数据 + AI 分析 + 联网搜索 |
| 06 | X 舆情综述 | DB 中已处理的 X 推文 | 系统数据 + AI 分析（不联网） |
| 07 | 个股评分 | yfinance 技术分析评分 | 无 AI（纯计算） |

> 注: 个股评分 Section 目前在前端隐藏（`display:none`），功能尚未完善。

## 两种 AI 模块模式

### 模式 A：系统数据 + AI 分析

- 后端先通过 Python 获取结构化数据（JSON）
- 将数据作为 `user_prompt` 传给 LLM
- `system_prompt` 描述数据格式 + 输出要求
- 使用 `web_search=True` 让 AI 补充联网信息
- 代表模块: 大盘综述、国债收益率、行业板块

### 模式 B：纯 LLM 联网搜索

- 无系统数据注入
- `user_prompt` 是一个固定的分析指令（如"请分析本周美股资金面情况..."）
- `system_prompt` 来自管理员配置（可为空）
- 使用 `web_search=True`，完全依赖 AI 联网搜索获取最新信息
- 代表模块: 资金面分析、国际局势

## 生成流程

```
generate_full_report(db, trigger, watchlist)
│
├── 1. 创建 DB 记录 (status=running)
│
├── 2. 并行获取数据（asyncio.gather）
│   ├── fetch_index_data()        → 三大指数 5 日行情 + 量比 + P/E
│   ├── fetch_sector_data()       → 11 个行业 ETF 5d/15d/30d 表现
│   ├── fetch_yield_curve_data()  → 国债收益率 + 利差 + 跨资产 + 形态判定
│   ├── fetch_x_tweets_data()     → 过去 7 天已处理推文聚合
│   └── get_report_section_stocks() → 个股评分
│
├── 3. 并行 AI 分析（asyncio.gather，6 个模块）
│   ├── generate_ai_market_summary(index_data)
│   ├── generate_ai_capital_summary()           ← 纯 LLM
│   ├── generate_ai_geopolitics_summary()       ← 纯 LLM
│   ├── generate_ai_sector_summary(sector_data)
│   ├── generate_ai_yield_curve_summary(curve_data)
│   └── generate_ai_x_monitor_summary(x_data)  ← 不联网
│
├── 4. 序列化 JSON 写入 DB
│
└── 5. 更新 status=completed / failed
```

## Prompt 管理

### 设计原则

- **代码中不硬编码分析指令**
- 所有 prompt 存在 `report_config` 表中，通过 `/report-admin` 页面配置
- 代码中的 `DEFAULT_*_SYSTEM_PROMPT` 常量只是初始值/兜底值
- 纯 LLM 模块的默认 prompt 为空字符串（管理员可自定义输出要求）

### Prompt 解析流程

```python
_resolve_prompts(config) → 7-tuple:
  (market, capital, geopolitics, sector, stocks, yield_curve, x_monitor)
```

优先使用 DB 中配置的 prompt，为空时回退到代码常量。

### Prompt 审计

每次生成周报时，使用的 prompt 会快照保存到 `weekly_reports` 表的 `*_system_prompt` 字段，用于事后审计和复现。

## 数据获取细节

### 大盘指数 (`fetch_index_data`)

- 标的: `^GSPC`(S&P500)、`^DJI`(道琼斯)、`^IXIC`(纳斯达克)
- 获取: 5 日收盘价（sparkline）、周涨跌幅、近 5 日量比、Forward/Trailing PE
- PE 数据: 先从指数获取，为空则用代理 ETF（SPY/DIA/QQQ）

### 行业板块 (`fetch_sector_data`)

- 标的: 11 个 SPDR 行业 ETF（XLK/XLF/XLE/XLV...）
- 获取: 5 日/15 日/30 日涨跌幅、当前价、量比
- 按周涨跌幅降序排列

### 国债收益率 (`fetch_yield_curve_data`)

- 标的: ^IRX(3M)、2YY=F(2Y)、^FVX(5Y)、^TNX(10Y)、^TYX(30Y)
- 直接调用 Yahoo Finance chart API（绕过 yfinance 限频）
- 计算: 各期限周变化（基点）、利差（2s10s/3m10s/10s30s）
- 形态判定: 四象限框架（Bear/Bull × Steepener/Flattener）
- 跨资产: VIX、DXY、GLD、CL=F、SPY 周变化

### 个股评分 (`score_stocks`)

- 使用 `StockAnalyzer` 计算技术指标（KDJ/MACD/RSI/MA）
- 生成 1-5 分评分 + 评级（AA/A/B/C/D）
- 热门股从 `HOT_STOCKS` 池按动量筛选 top 10

## 前端展示

- 周报查看页: `/scoring`（`report_api.py`）
- 使用 `marked.js` 渲染 Markdown + `KaTeX` 渲染 LaTeX
- `renderMd()` helper 先保护 LaTeX 块，再用 marked 解析，最后恢复 LaTeX
- 版本切换: 可查看历史版本

## 定时生成

- 配置存在 `report_config` 表
- 默认: 每周五美东 17:00
- 通过 APScheduler CronTrigger 调度
- 支持 weekly / daily 频率
