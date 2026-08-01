"""持仓 / 交易日志 / 仓位计算 REST API（前端 SPA: PortfolioPage.tsx）

- 交易日志：买卖流水 CRUD，按用户隔离
- 持仓：平均成本法聚合 + 实时行情 + 止损距离 + R-multiple + RS 排名
- 仓位计算器：固定风险法，风险 % 与市场红绿灯联动
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.auth import get_current_user
from app.market.regime import get_current_risk_pct
from app.portfolio.service import aggregate_positions, suggest_position_size
from db.models import (
    SessionLocal, User, PortfolioSettings, TradeRecord, PositionStop,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

VALID_SETUPS = {"vcp_breakout", "pullback", "breakout", "other", ""}


# ─── Pydantic 模型 ───

class SettingsUpdate(BaseModel):
    account_size: float
    risk_pct_green: float = 1.0
    risk_pct_yellow: float = 0.5
    risk_pct_red: float = 0.25
    max_position_pct: float = 25.0
    max_positions: int = 8

    @field_validator("account_size")
    @classmethod
    def _positive_account(cls, v):
        if v <= 0:
            raise ValueError("账户资金必须为正数")
        return v


class TradeCreate(BaseModel):
    symbol: str
    side: str                    # buy / sell
    qty: float
    price: float
    commission: float = 0.0
    trade_date: str              # YYYY-MM-DD
    setup: str = ""
    initial_stop: Optional[float] = None
    note: str = ""

    @field_validator("side")
    @classmethod
    def _valid_side(cls, v):
        if v not in ("buy", "sell"):
            raise ValueError("side 必须为 buy 或 sell")
        return v

    @field_validator("qty", "price")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("数量与价格必须为正数")
        return v

    @field_validator("trade_date")
    @classmethod
    def _valid_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("trade_date 格式必须为 YYYY-MM-DD")
        return v


class StopUpdate(BaseModel):
    stop_price: float

    @field_validator("stop_price")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("止损价必须为正数")
        return v


class PositionSizeRequest(BaseModel):
    entry: float
    stop: float
    risk_pct: Optional[float] = None   # 不传则按红绿灯自动取


# ─── 内部工具 ───

def _get_or_create_settings(db, user_id: int) -> PortfolioSettings:
    row = db.query(PortfolioSettings).filter_by(user_id=user_id).first()
    if not row:
        row = PortfolioSettings(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _settings_dict(row: PortfolioSettings) -> dict:
    return {
        "account_size": row.account_size,
        "risk_pct_green": row.risk_pct_green,
        "risk_pct_yellow": row.risk_pct_yellow,
        "risk_pct_red": row.risk_pct_red,
        "max_position_pct": row.max_position_pct,
        "max_positions": row.max_positions,
    }


# ─── 设置 ───

@router.get("/api/portfolio/settings")
async def get_settings(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        return {"settings": _settings_dict(_get_or_create_settings(db, current_user.id))}
    finally:
        db.close()


@router.put("/api/portfolio/settings")
async def update_settings(
    req: SettingsUpdate,
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        row = _get_or_create_settings(db, current_user.id)
        row.account_size = req.account_size
        row.risk_pct_green = req.risk_pct_green
        row.risk_pct_yellow = req.risk_pct_yellow
        row.risk_pct_red = req.risk_pct_red
        row.max_position_pct = req.max_position_pct
        row.max_positions = req.max_positions
        db.commit()
        return {"success": True, "settings": _settings_dict(row)}
    finally:
        db.close()


# ─── 交易日志 ───

@router.post("/api/portfolio/trades")
async def create_trade(
    req: TradeCreate,
    current_user: User = Depends(get_current_user),
):
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol 不能为空")
    setup = req.setup if req.setup in VALID_SETUPS else "other"

    db = SessionLocal()
    try:
        trade = TradeRecord(
            user_id=current_user.id,
            symbol=sym,
            side=req.side,
            qty=req.qty,
            price=req.price,
            commission=max(0.0, req.commission),
            trade_date=req.trade_date,
            setup=setup,
            initial_stop=req.initial_stop,
            note=(req.note or "")[:500],
        )
        db.add(trade)
        # 买入带止损时，同步 upsert 持仓止损价
        if req.side == "buy" and req.initial_stop:
            stop_row = db.query(PositionStop).filter_by(
                user_id=current_user.id, symbol=sym).first()
            if stop_row:
                stop_row.stop_price = req.initial_stop
            else:
                db.add(PositionStop(user_id=current_user.id, symbol=sym,
                                    stop_price=req.initial_stop))
        db.commit()
        return {"success": True, "id": trade.id}
    finally:
        db.close()


@router.get("/api/portfolio/trades")
async def list_trades(
    symbol: str = Query("", description="按标的过滤"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        q = db.query(TradeRecord).filter_by(user_id=current_user.id)
        if symbol.strip():
            q = q.filter(TradeRecord.symbol == symbol.strip().upper())
        total = q.count()
        rows = (q.order_by(TradeRecord.trade_date.desc(), TradeRecord.id.desc())
                .offset(offset).limit(limit).all())
        return {
            "total": total,
            "trades": [{
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "price": t.price,
                "commission": t.commission,
                "trade_date": t.trade_date,
                "setup": t.setup,
                "initial_stop": t.initial_stop,
                "note": t.note,
            } for t in rows],
        }
    finally:
        db.close()


@router.delete("/api/portfolio/trades/{trade_id}")
async def delete_trade(
    trade_id: int,
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        trade = db.query(TradeRecord).filter_by(
            id=trade_id, user_id=current_user.id).first()
        if not trade:
            raise HTTPException(status_code=404, detail="交易记录不存在")
        db.delete(trade)
        db.commit()
        return {"success": True}
    finally:
        db.close()


# ─── 持仓 ───

@router.get("/api/portfolio/positions")
async def get_positions(current_user: User = Depends(get_current_user)):
    """聚合持仓 + 实时行情 + 止损距离 + R-multiple + RS 排名"""
    db = SessionLocal()
    try:
        trades = db.query(TradeRecord).filter_by(user_id=current_user.id).all()
        agg = aggregate_positions(trades)
        settings = _get_or_create_settings(db, current_user.id)
        stops = {s.symbol: s.stop_price for s in
                 db.query(PositionStop).filter_by(user_id=current_user.id).all()}
    finally:
        db.close()

    positions = agg["positions"]
    symbols = [p["symbol"] for p in positions]

    # 实时行情（复用 watchlist 的批量快照）
    quotes: dict[str, dict] = {}
    if symbols:
        from app.api.watchlist_api import _fetch_quotes_sync
        quotes = await asyncio.to_thread(_fetch_quotes_sync, symbols)

    # RS 排名（读缓存，不触发全量重算）
    rs_snap: dict[str, float] = {}
    try:
        from app.data.rs_rating import get_rs_snapshot
        rs_snap = get_rs_snapshot() or {}
    except Exception:
        pass

    total_market_value = 0.0
    total_unrealized = 0.0
    total_open_risk = 0.0
    for p in positions:
        sym = p["symbol"]
        quote = quotes.get(sym) or {}
        price = quote.get("price")
        stop = stops.get(sym) or p.get("initial_stop")
        p["current_price"] = price
        p["change_pct"] = quote.get("change_pct")
        p["stop_price"] = stop
        p["rs_percentile"] = rs_snap.get(sym)
        if price:
            mv = price * p["qty"]
            unrealized = (price - p["avg_cost"]) * p["qty"]
            p["market_value"] = round(mv, 2)
            p["unrealized_pnl"] = round(unrealized, 2)
            p["unrealized_pct"] = round((price / p["avg_cost"] - 1) * 100, 2)
            total_market_value += mv
            total_unrealized += unrealized
            if stop:
                p["stop_distance_pct"] = round((price - stop) / price * 100, 2)
                open_risk = max(0.0, (price - stop)) * p["qty"] if price > stop else 0.0
                # 敞口风险：当前价到止损的潜在损失（价格低于止损则为 0）
                p["open_risk"] = round(open_risk, 2)
                total_open_risk += open_risk
                risk_base = p["avg_cost"] - stop
                p["r_multiple"] = round((price - p["avg_cost"]) / risk_base, 2) if risk_base > 0 else None
            else:
                p["stop_distance_pct"] = None
                p["open_risk"] = None
                p["r_multiple"] = None
        else:
            p["market_value"] = None
            p["unrealized_pnl"] = None
            p["unrealized_pct"] = None
            p["stop_distance_pct"] = None
            p["open_risk"] = None
            p["r_multiple"] = None

    return {
        "positions": positions,
        "closed": agg["closed"],
        "warnings": agg["warnings"],
        "summary": {
            "position_count": len(positions),
            "max_positions": settings.max_positions,
            "account_size": settings.account_size,
            "total_market_value": round(total_market_value, 2),
            "exposure_pct": round(total_market_value / settings.account_size * 100, 1)
                            if settings.account_size else None,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_realized_pnl": agg["total_realized_pnl"],
            "total_open_risk": round(total_open_risk, 2),
            "open_risk_pct": round(total_open_risk / settings.account_size * 100, 2)
                             if settings.account_size else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/api/portfolio/positions/{symbol}/stop")
async def update_position_stop(
    symbol: str,
    req: StopUpdate,
    current_user: User = Depends(get_current_user),
):
    sym = symbol.strip().upper()
    db = SessionLocal()
    try:
        row = db.query(PositionStop).filter_by(
            user_id=current_user.id, symbol=sym).first()
        if row:
            row.stop_price = req.stop_price
        else:
            db.add(PositionStop(user_id=current_user.id, symbol=sym,
                                stop_price=req.stop_price))
        db.commit()
        return {"success": True, "symbol": sym, "stop_price": req.stop_price}
    finally:
        db.close()


# ─── 仓位计算器 ───

@router.post("/api/portfolio/position-size")
async def position_size(
    req: PositionSizeRequest,
    current_user: User = Depends(get_current_user),
):
    """固定风险法仓位建议；risk_pct 不传时按市场红绿灯自动取值"""
    db = SessionLocal()
    try:
        settings = _get_or_create_settings(db, current_user.id)
    finally:
        db.close()

    regime_state = None
    risk_pct = req.risk_pct
    if risk_pct is None:
        risk_pct, regime_state = get_current_risk_pct(settings)

    try:
        result = suggest_position_size(
            account_size=settings.account_size,
            risk_pct=risk_pct,
            entry=req.entry,
            stop=req.stop,
            max_position_pct=settings.max_position_pct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result["risk_pct"] = risk_pct
    result["regime_state"] = regime_state
    result["account_size"] = settings.account_size
    return result
