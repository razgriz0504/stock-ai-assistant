"""板块强度雷达 - ETF 前十大持仓拉取

统一门面：
- fetch_holdings(market, symbol) -> dict

数据源：
- 美股：yfinance.Ticker(symbol).funds_data.top_holdings
- A 股：akshare.fund_portfolio_hold_em(symbol, date)

缓存策略：季报/月报级数据变化慢，TTL 24 小时；
按 (market, symbol) 独立缓存，减少上游压力。
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 缓存: {(market, symbol): {"data": {...}, "ts": float}}
_holdings_cache: dict[tuple[str, str], dict] = {}
_CACHE_TTL = 24 * 3600  # 24 小时


def _cached(market: str, symbol: str) -> Optional[dict]:
    entry = _holdings_cache.get((market, symbol))
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _save_cache(market: str, symbol: str, data: dict) -> None:
    _holdings_cache[(market, symbol)] = {"data": data, "ts": time.time()}


# ─── 美股：yfinance ───

def fetch_holdings_us(symbol: str) -> dict:
    """获取美股 ETF 前十大持仓（yfinance funds_data）。

    Returns:
        {
            "symbol": "XLK",
            "market": "us",
            "holdings": [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": 22.5},
                ...
            ],
            "as_of": "2024-Q3",  # yfinance 不总返回日期，尽力而为
            "source": "yfinance",
        }
    """
    cached = _cached("us", symbol)
    if cached is not None:
        return cached

    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        funds = getattr(ticker, "funds_data", None)
        if funds is None:
            raise ValueError("no funds_data")

        top = funds.top_holdings
        if top is None or top.empty:
            raise ValueError("empty top_holdings")

        holdings = []
        # top_holdings 索引通常是 symbol，列有 "Holding Name" / "Holding Percent"
        # yfinance 版本差异较大，做鲁棒解析
        for idx, row in top.iterrows():
            sym = str(idx) if idx is not None else ""
            name = ""
            pct: Optional[float] = None
            for col in ("Holding Name", "holdingName", "name"):
                if col in row.index:
                    name = str(row[col])
                    break
            for col in ("Holding Percent", "holdingPercent", "weight"):
                if col in row.index:
                    try:
                        raw = float(row[col])
                        # 有的返回小数（0.225），有的返回百分数（22.5），统一到百分数
                        pct = raw * 100 if abs(raw) < 1.5 else raw
                    except (TypeError, ValueError):
                        pass
                    break
            if sym and pct is not None:
                holdings.append({
                    "symbol": sym,
                    "name": name,
                    "weight": round(pct, 2),
                })

        result = {
            "symbol": symbol,
            "market": "us",
            "holdings": holdings[:10],
            "as_of": "",
            "source": "yfinance",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_cache("us", symbol, result)
        return result

    except Exception as e:
        logger.warning(f"fetch_holdings_us({symbol}) failed: {e}")
        return {
            "symbol": symbol,
            "market": "us",
            "holdings": [],
            "as_of": "",
            "source": "yfinance",
            "error": str(e),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


# ─── A 股：akshare ───

def fetch_holdings_cn(symbol: str) -> dict:
    """获取 A 股 ETF 前十大持仓（akshare fund_portfolio_hold_em）。

    akshare 返回列（中文）:
        序号 / 股票代码 / 股票名称 / 占净值比例 / 持股数 / 持仓市值 / 季度

    只保留最近一个季度的前 10 大。
    """
    cached = _cached("cn", symbol)
    if cached is not None:
        return cached

    try:
        import akshare as ak
        # date 传当前年份，akshare 返回可用季度
        year = str(datetime.now().year)
        raw = ak.fund_portfolio_hold_em(symbol=symbol, date=year)
        if raw is None or raw.empty:
            # 尝试上一年
            raw = ak.fund_portfolio_hold_em(symbol=symbol, date=str(int(year) - 1))

        if raw is None or raw.empty:
            raise ValueError("empty portfolio")

        # 选最新季度
        latest_quarter = None
        if "季度" in raw.columns:
            quarters = raw["季度"].dropna().unique().tolist()
            if quarters:
                # 季度字符串形如 "2024年3季度股票投资明细"，按字符串倒序即可近似"最新"
                quarters_sorted = sorted(quarters, reverse=True)
                latest_quarter = quarters_sorted[0]
                raw = raw[raw["季度"] == latest_quarter]

        holdings = []
        for _, row in raw.head(10).iterrows():
            code = str(row.get("股票代码", "")).strip()
            name = str(row.get("股票名称", "")).strip()
            try:
                weight = float(row.get("占净值比例", 0))
            except (TypeError, ValueError):
                weight = 0.0
            if code:
                holdings.append({
                    "symbol": code,
                    "name": name,
                    "weight": round(weight, 2),
                })

        result = {
            "symbol": symbol,
            "market": "cn",
            "holdings": holdings,
            "as_of": latest_quarter or "",
            "source": "akshare",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_cache("cn", symbol, result)
        return result

    except Exception as e:
        logger.warning(f"fetch_holdings_cn({symbol}) failed: {e}")
        return {
            "symbol": symbol,
            "market": "cn",
            "holdings": [],
            "as_of": "",
            "source": "akshare",
            "error": str(e),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


# ─── 统一门面 ───

def fetch_holdings(market: str, symbol: str) -> dict:
    """按市场分派到对应的持仓拉取函数。"""
    if market == "cn":
        return fetch_holdings_cn(symbol)
    return fetch_holdings_us(symbol)
