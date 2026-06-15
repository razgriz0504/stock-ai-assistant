"""关注列表 REST API（前端 SPA: WatchlistPage.tsx）

数据存储格式（向前兼容）:
- 旧: ["AAPL", "TSLA"]                字符串数组
- 新: [{symbol, source, added_at, note}]  对象数组,带来源标签

读取时自动统一为对象格式;写入时优先用对象格式持久化。
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.models import SessionLocal, UserPreference, XTweet

logger = logging.getLogger(__name__)
router = APIRouter()

WEB_USER_ID = "web_default"

# ─── Pydantic 模型 ───


class WatchlistUpdate(BaseModel):
    """旧接口:整体替换(兼容历史前端)"""
    stocks: list[str]


class WatchlistAddRequest(BaseModel):
    """添加单只股票"""
    symbol: str
    source: str = "manual"   # manual / screener:<preset_name> / report / dashboard
    note: Optional[str] = ""


class WatchlistRemoveRequest(BaseModel):
    symbol: str


# ─── 内部工具 ───


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_item(raw) -> dict:
    """统一为 {symbol, source, added_at, note} 对象"""
    if isinstance(raw, str):
        return {
            "symbol": raw.strip().upper(),
            "source": "manual",
            "added_at": _now_iso(),
            "note": "",
        }
    if isinstance(raw, dict):
        return {
            "symbol": str(raw.get("symbol", "")).strip().upper(),
            "source": str(raw.get("source") or "manual"),
            "added_at": str(raw.get("added_at") or _now_iso()),
            "note": str(raw.get("note") or ""),
        }
    return {"symbol": "", "source": "manual", "added_at": _now_iso(), "note": ""}


def _load_items(pref: Optional[UserPreference]) -> list[dict]:
    if not pref or not pref.watchlist:
        return []
    try:
        raw = json.loads(pref.watchlist)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    items = [_normalize_item(x) for x in raw]
    return [it for it in items if it["symbol"]]


def _save_items(db, items: list[dict]) -> None:
    pref = db.query(UserPreference).filter(
        UserPreference.feishu_user_id == WEB_USER_ID
    ).first()
    payload = json.dumps(items, ensure_ascii=False)
    if not pref:
        pref = UserPreference(feishu_user_id=WEB_USER_ID, watchlist=payload)
        db.add(pref)
    else:
        pref.watchlist = payload
    db.commit()


# ─── API 接口 ───


@router.get("/api/watchlist")
async def get_watchlist():
    """获取当前关注列表(同时返回旧/新两种字段以兼容)"""
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        items = _load_items(pref)
        return {
            "stocks": [it["symbol"] for it in items],   # 兼容旧前端
            "items": items,                              # 新前端使用
        }
    finally:
        db.close()


@router.post("/api/watchlist")
async def update_watchlist(req: WatchlistUpdate):
    """整体替换(旧接口,兼容已有 WatchlistPage)"""
    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        existing = {it["symbol"]: it for it in _load_items(pref)}

        # 去重+大写,保留旧 source/added_at,缺失则新建
        new_items: list[dict] = []
        seen: set[str] = set()
        for s in req.stocks:
            sym = (s or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            if sym in existing:
                new_items.append(existing[sym])
            else:
                new_items.append({
                    "symbol": sym,
                    "source": "manual",
                    "added_at": _now_iso(),
                    "note": "",
                })

        _save_items(db, new_items)
        return {
            "success": True,
            "stocks": [it["symbol"] for it in new_items],
            "items": new_items,
        }
    finally:
        db.close()


@router.post("/api/watchlist/add")
async def add_watchlist(req: WatchlistAddRequest):
    """添加单只股票(已存在则更新 source/note)"""
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        items = _load_items(pref)

        already_exists = False
        for it in items:
            if it["symbol"] == sym:
                already_exists = True
                # 已存在不覆盖原始 source/added_at,仅追加备注
                if req.note:
                    it["note"] = req.note
                break

        if not already_exists:
            items.append({
                "symbol": sym,
                "source": req.source or "manual",
                "added_at": _now_iso(),
                "note": req.note or "",
            })

        _save_items(db, items)
        return {
            "success": True,
            "already_exists": already_exists,
            "items": items,
        }
    finally:
        db.close()


@router.post("/api/watchlist/remove")
async def remove_watchlist(req: WatchlistRemoveRequest):
    """移除单只股票"""
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    db = SessionLocal()
    try:
        pref = db.query(UserPreference).filter(
            UserPreference.feishu_user_id == WEB_USER_ID
        ).first()
        items = _load_items(pref)
        new_items = [it for it in items if it["symbol"] != sym]
        removed = len(items) != len(new_items)
        _save_items(db, new_items)
        return {
            "success": True,
            "removed": removed,
            "items": new_items,
        }
    finally:
        db.close()


# ─── 行情快照接口 ───


def _fetch_quotes_sync(symbols: list[str]) -> dict[str, dict]:
    """批量拉取行情快照: {symbol: {price, prev_close, change_pct, name}}"""
    if not symbols:
        return {}
    try:
        import yfinance as yf
    except Exception as e:
        logger.warning(f"[watchlist] yfinance import failed: {e}")
        return {}

    result: dict[str, dict] = {}
    try:
        # 拉 5d 历史,用最后两根 K 线算日涨跌
        data = yf.download(
            symbols,
            period="5d",
            progress=False,
            threads=True,
            group_by="ticker",
            auto_adjust=False,
        )
        if data is None or data.empty:
            return {}

        import pandas as pd
        single = len(symbols) == 1

        for sym in symbols:
            try:
                if single:
                    df = data
                else:
                    if isinstance(data.columns, pd.MultiIndex):
                        # group_by='ticker' 时第 0 层是 ticker
                        if sym in data.columns.get_level_values(0):
                            df = data[sym]
                        elif sym in data.columns.get_level_values(1):
                            df = data.xs(sym, level=1, axis=1)
                        else:
                            continue
                    else:
                        continue
                close_series = df["Close"].dropna() if "Close" in df.columns else None
                if close_series is None or close_series.empty:
                    continue
                price = float(close_series.iloc[-1])
                prev = float(close_series.iloc[-2]) if len(close_series) >= 2 else price
                chg_pct = ((price - prev) / prev * 100.0) if prev else 0.0
                result[sym] = {
                    "price": round(price, 2),
                    "prev_close": round(prev, 2),
                    "change_pct": round(chg_pct, 2),
                }
            except Exception as e:
                logger.debug(f"[watchlist] quote parse failed for {sym}: {e}")
                continue
    except Exception as e:
        logger.warning(f"[watchlist] yf.download failed: {e}")

    return result


@router.get("/api/watchlist/quotes")
async def watchlist_quotes(symbols: str = Query("", description="逗号分隔的股票代码")):
    """批量行情快照,前端只用一次请求拿到所有关注股的最新价/涨跌幅"""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    syms = list(dict.fromkeys(syms))[:60]   # 去重 + 上限保护
    if not syms:
        return {"quotes": {}}
    quotes = await asyncio.to_thread(_fetch_quotes_sync, syms)
    return {
        "quotes": quotes,
        "generated_at": _now_iso(),
    }


# ─── X 舆情聚合接口 ───


def _normalize_asset(asset: str) -> str:
    """X 推文中的 impact_assets 可能是 'AAPL' / '$AAPL' / 'Apple Inc.' 等,统一成大写 ticker"""
    if not asset:
        return ""
    s = str(asset).strip().upper().lstrip("$").strip()
    # 只保留可能的 ticker(字母数字 + . -),其它视为公司名
    if not s or len(s) > 8:
        return ""
    if not all(c.isalnum() or c in ".-" for c in s):
        return ""
    return s


@router.get("/api/watchlist/sentiment")
async def watchlist_sentiment(
    symbols: str = Query("", description="逗号分隔的股票代码"),
    days: int = Query(7, ge=1, le=90, description="统计窗口天数"),
):
    """聚合关注列表中每只股票的最近 X 推文舆情:
    返回 {symbol: {bullish, bearish, neutral, total, latest: {...}}}
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    syms = list(dict.fromkeys(syms))[:60]
    if not syms:
        return {"sentiment": {}, "days": days}

    sym_set = set(syms)
    result: dict[str, dict] = {
        s: {"bullish": 0, "bearish": 0, "neutral": 0, "total": 0, "latest": None}
        for s in syms
    }

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        # 仅取已 AI 处理过的推文(有 impact_assets)
        tweets = (
            db.query(XTweet)
            .filter(XTweet.created_at_x >= cutoff)
            .filter(XTweet.processed == True)  # noqa: E712
            .filter(XTweet.impact_assets.isnot(None))
            .order_by(XTweet.created_at_x.desc())
            .limit(500)
            .all()
        )

        for t in tweets:
            try:
                assets = json.loads(t.impact_assets) if t.impact_assets else []
            except Exception:
                continue
            if not isinstance(assets, list):
                continue
            sentiment = (t.sentiment or "neutral").lower()
            bucket = "bullish" if sentiment == "bullish" else "bearish" if sentiment == "bearish" else "neutral"

            # 一条推文若同时影响多只关注股,各计 1 次
            seen_in_tweet: set[str] = set()
            for a in assets:
                norm = _normalize_asset(a)
                if not norm or norm in seen_in_tweet:
                    continue
                if norm not in sym_set:
                    continue
                seen_in_tweet.add(norm)
                cell = result[norm]
                cell[bucket] += 1
                cell["total"] += 1
                # 保留最新一条(因为按 desc 排序,只在第一次记录)
                if cell["latest"] is None:
                    cell["latest"] = {
                        "tweet_id": t.tweet_id,
                        "username": t.username,
                        "sentiment": sentiment,
                        "text_zh": (t.text_zh or t.text or "")[:120],
                        "created_at_x": t.created_at_x.isoformat() if t.created_at_x else None,
                    }
    finally:
        db.close()

    return {
        "sentiment": result,
        "days": days,
        "generated_at": _now_iso(),
    }
