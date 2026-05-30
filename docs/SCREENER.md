# Stock Screener - 选股器

## 概述

批量扫描美股大盘（S&P 500 + Nasdaq 100 并集，约 550 只），通过可配置的技术面 + 基本面过滤器筛选出符合条件的股票。

## 股票池（Universe）

- **来源**: 实时从 Wikipedia 抓取 S&P 500 和 Nasdaq 100 成分股列表
- **缓存**: 24 小时
- **降级**: Wikipedia 不可访问时使用代码中的 fallback 列表
- **代码**: `app/screener/universe.py`

## 执行流程

```
screener/engine.py → run_screener()
│
├── 1. 获取股票池（get_universe → ~550 只）
├── 2. 创建 DB 记录 (status=running)
├── 3. 并行批量处理（ThreadPoolExecutor）
│   ├── 获取每只股票的历史行情 (6mo)
│   ├── 计算技术指标（pandas_ta）
│   ├── 获取基本面数据（yfinance info）
│   ├── 应用过滤器（technical + fundamental）
│   └── 计算技术评分
├── 4. 结果写入 screener_results 表
├── 5. 更新进度 (progress_pct) 和状态
└── 6. 完成/失败
```

## 过滤器体系

### 技术面过滤器 (`filters.py`)

| 过滤器 | 功能 | 参数 |
|--------|------|------|
| `filter_ma_arrangement` | 均线多/空头排列（日线 + 周线双时间框架 EMA） | `direction: bullish/bearish` |
| `filter_macd_golden_cross` | MACD 金叉 | `lookback: N bars` |
| `filter_kdj_oversold_bounce` | KDJ 超卖反弹（J 从 <20 向上穿越） | `lookback: N bars` |
| `filter_volume_breakout` | 放量突破（当日成交量 > N 倍 20 日均量） | `multiplier: 2.0` |
| `filter_bb_squeeze` | 布林带收窄（带宽 < 阈值） | `threshold: 0.15` |
| `filter_rsi_range` | RSI 区间筛选 | `min, max` |
| `filter_trend_initiation` | 趋势启动（从整理区间突破） | 自动检测 |

### 基本面过滤器

| 过滤器 | 功能 | 参数 |
|--------|------|------|
| `filter_market_cap` | 市值筛选 | `min, max` |
| `filter_pe_ratio` | 市盈率范围 | `min, max` |
| `filter_revenue_growth` | 营收增长率 | `min` |
| `filter_roe` | 净资产收益率 | `min` |
| `filter_dividend_yield` | 股息率 | `min` |

### 过滤器签名统一

```python
filter_xxx(df: DataFrame, info: dict, params: dict) -> bool
```

- `df`: 带技术指标的 OHLCV DataFrame
- `info`: yfinance 基本面数据字典
- `params`: 用户配置的参数

## 预设管理

- 过滤器组合可保存为"预设"（`screener_presets` 表）
- 包含: 预设名称、筛选条件 JSON、自定义代码
- 支持设为默认预设

## 定时运行

- 配置存在 `screener_config` 表
- 支持 daily / weekly 频率
- 指定运行的预设 ID

## 结果存储

每只股票的结果保存在 `screener_results` 表：
- `passed`: 是否通过所有过滤器
- `score`: 技术评分 1-5
- `rating`: AA/A/B/C/D
- `filter_details_json`: 各过滤器通过/失败详情
- `indicators_json`: 关键指标值快照

## 前端页面

- URL: `/screener`
- 功能: 配置过滤器、手动触发、查看结果、管理预设
- 结果展示: 表格 + 中文名 + 行业分类
