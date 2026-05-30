# 重要设计决策记录

本文档记录项目中的关键设计决策，帮助理解"为什么这么做"。

---

## D001: Prompt 不硬编码在后端代码中

**背景**: 早期版本将分析指令直接写在 Python 代码里，每次调整都要改代码重启。

**决策**: 
- 所有 AI 分析的 system_prompt 存入数据库 `report_config` 表
- 通过 `/report-admin` 管理页面可随时修改
- 代码中的 `DEFAULT_*_SYSTEM_PROMPT` 常量仅作为首次初始化的兜底值
- 每次生成报告时，使用的 prompt 快照保存到 `weekly_reports` 表（审计用）

**结果**: 可以在不重启服务的情况下调整 AI 的分析角度和输出格式。

---

## D002: 纯 LLM 模块 vs 数据注入模块

**背景**: 并非所有分析都需要系统预先获取数据。

**决策**:
- **数据注入模块**（大盘、行业、国债、X 舆情）: Python 先获取结构化数据，作为 user_prompt 传给 AI
- **纯 LLM 模块**（资金面、国际局势）: 不注入任何系统数据，依赖 AI 联网搜索自行获取最新信息
- 纯 LLM 模块的默认 system_prompt 为空字符串，给管理员最大灵活度

**理由**: 资金面和国际局势的数据来源广泛（美联储声明、政策新闻等），不适合用简单的 API 抓取，AI 联网搜索更合适。

---

## D003: 前端 HTML 内嵌在 Python 文件中

**背景**: 项目前端不复杂，不需要独立前端框架。

**决策**: 每个 Web 页面的 HTML/CSS/JS 直接写在对应的 `app/api/*.py` 路由文件中，通过 `HTMLResponse` 返回。

**优点**:
- 单文件包含路由逻辑 + API + 前端，改动集中
- 无需构建步骤、无需模板引擎
- 部署简单（只有 Python 文件）

**缺点**: 文件较长，Python 与 HTML 混合

---

## D004: SQLite 自动迁移方案

**背景**: 生产服务器已有运行中的 SQLite 数据库，新增列会导致 500 错误。

**决策**: 在 `init_db()` 中加入 `_migrate_missing_columns()` 函数：
- 用 `PRAGMA table_info` 检测现有列
- 对缺失的列执行 `ALTER TABLE ADD COLUMN`
- 新增迁移项只需在 `migrations` 列表中追加一行

**理由**: SQLite 不支持 `ADD COLUMN IF NOT EXISTS`，也不想引入 Alembic 这样的重型迁移框架。

---

## D005: Gemini Google Search Grounding

**背景**: AI 生成的分析内容需要引用最新数据。

**决策**: 
- 使用 Gemini 的 Google Search grounding 功能: `tools=[{"google_search": {}}]`
- 通过 LiteLLM 的 `_hidden_params.vertex_ai_grounding_metadata` 提取引用来源
- 自动在文本中插入 `[1](url)` 格式的内联引用
- 文末追加去重的数据来源列表

**注意**: 此功能仅 Gemini 模型支持。切换到其他模型时 `web_search=True` 不会报错但也不会联网。

---

## D006: 选股器使用 Wikipedia 作为成分股来源

**背景**: 需要 S&P 500 和 Nasdaq 100 的最新成分股列表。

**决策**: 
- 从 Wikipedia 实时抓取成分股表格
- 24 小时缓存
- 内置 fallback 列表（Wikipedia 不可用时兜底）

**理由**: 避免依赖付费 API，Wikipedia 数据更新及时且稳定。

---

## D007: 国债收益率使用 Yahoo Finance Chart API

**背景**: yfinance 库对国债收益率数据有限频问题。

**决策**: 直接调用 Yahoo Finance 的 chart REST API（`query1.finance.yahoo.com/v8/finance/chart/`），带自定义 User-Agent。

**理由**: 更可靠，避免 yfinance 库的限频和 404 问题。

---

## D008: X 推文 AI 处理 — 严格 JSON 输出

**背景**: LLM 输出格式不稳定，有时带 markdown 代码块或多余文字。

**决策**: 
- Prompt 中明确要求"仅返回单一 JSON 对象"
- 解析时先 `_strip_code_fence()` 去掉 ``` 包裹
- 再用正则 `\{.*\}` 兜底提取第一个 JSON 块
- 最后 `_normalize()` 确保所有字段都有合理默认值

---

## D009: 并发控制策略

**背景**: 多个模块都涉及批量 API 调用。

**决策**:
- 周报数据获取: `ThreadPoolExecutor(max_workers=5)` 并行拉取行情
- AI 分析: `asyncio.gather` 并行调用 6 个 LLM 任务
- X 推文处理: `asyncio.Semaphore(3)` 限制并发
- 选股器: `ThreadPoolExecutor` 批量处理 550 只股票

**理由**: 平衡速度和 API 限频，避免被上游数据源封禁。

---

## D010: 安全过滤降级（Gemini）

**背景**: Gemini 对金融话题（涉及投资建议、市场波动）的 SAFETY 过滤过于激进，经常返回空内容。

**决策**: 配置 `safety_settings` 将多项类别的阈值设为 `BLOCK_NONE`（仅 `DANGEROUS_CONTENT` 保留 `BLOCK_ONLY_HIGH`）。

**代码位置**: `app/llm/client.py` 的 `_GEMINI_SAFETY_SETTINGS`

---

*每次做出重要设计决策时，应在此文档追加新条目。*
