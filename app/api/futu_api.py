"""富途 OpenD 只读 API 路由。

设计约束：
  1. 本文件**只**暴露查询类接口。禁止新增 place_order / cancel_order /
     modify_order / unlock_trade 等交易变更端点。
  2. FUTU_ENABLED=false 时全部返回 503，前端菜单据此隐藏。
  3. 依赖 [futu_provider](file:///d:/Codes/stock-ai-assistant/app/data/futu_provider.py) 单例，
     所有异常已在 Provider 层吞掉，此处只负责序列化。
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from app.auth import require_admin
from app.data.futu_provider import futu_provider

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/futu",
    tags=["futu"],
    dependencies=[Depends(require_admin)],
)


# ─── 工具 ───

def _require_enabled():
    if not settings.futu_enabled:
        raise HTTPException(status_code=503, detail="Futu disabled (FUTU_ENABLED=false)")


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    # 处理 NaN → None，避免 JSON 序列化 NaN
    return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")


def _parse_codes(codes: str, limit: int = 50) -> list[str]:
    items = [c.strip() for c in (codes or "").split(",") if c.strip()]
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for c in items:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= limit:
            break
    return out


# ─── 状态 ───

@router.get("/status")
async def status():
    """探测 OpenD 连接与登录状态。前端据此决定是否显示 /futu 菜单。"""
    return {
        "enabled": settings.futu_enabled,
        "host": settings.futu_opend_host,
        "port": settings.futu_opend_port,
        "trd_env": settings.futu_trd_env,
        "trd_market": settings.futu_trd_market,
        "detail": futu_provider.status(),
    }


# ─── 行情 ───

@router.get("/snapshot")
async def snapshot(codes: str = Query("", description="逗号分隔，如 US.AAPL,HK.00700")):
    _require_enabled()
    code_list = _parse_codes(codes, limit=50)
    if not code_list:
        return {"records": [], "codes": []}
    df = futu_provider.get_snapshot(tuple(code_list))
    return {"codes": code_list, "records": _df_to_records(df)}


@router.get("/orderbook")
async def orderbook(
    code: str = Query(..., description="如 US.AAPL"),
    num: int = Query(10, ge=1, le=40),
):
    _require_enabled()
    data = futu_provider.get_order_book(code, num=num)
    return {"code": code, "data": data}


@router.get("/ticker")
async def ticker(
    code: str = Query(..., description="如 US.AAPL"),
    num: int = Query(100, ge=1, le=1000),
):
    _require_enabled()
    df = futu_provider.get_rt_ticker(code, num=num)
    return {"code": code, "records": _df_to_records(df)}


@router.get("/kline")
async def kline(
    code: str = Query(..., description="如 US.AAPL"),
    ktype: str = Query("K_DAY", description="K_1M/K_5M/K_15M/K_30M/K_60M/K_DAY/K_WEEK/K_MON"),
    start: str = Query("", description="YYYY-MM-DD"),
    end: str = Query("", description="YYYY-MM-DD"),
    max_count: int = Query(500, ge=1, le=1000),
):
    _require_enabled()
    df = futu_provider.get_kline(code, ktype=ktype, start=start, end=end, max_count=max_count)
    return {
        "code": code,
        "ktype": ktype,
        "records": _df_to_records(df),
    }


@router.get("/timeshare")
async def timeshare(code: str = Query(..., description="如 US.AAPL")):
    _require_enabled()
    df = futu_provider.get_rt_data(code)
    return {"code": code, "records": _df_to_records(df)}


# ─── 板块 ───

@router.get("/plate/list")
async def plate_list(
    market: str = Query("US", description="US/HK/SH/SZ"),
    plate_class: str = Query("INDUSTRY", description="INDUSTRY/REGION/CONCEPT/OTHER"),
):
    _require_enabled()
    df = futu_provider.get_plate_list(market=market, plate_class=plate_class)
    return {
        "market": market,
        "plate_class": plate_class,
        "records": _df_to_records(df),
    }


@router.get("/plate/stocks")
async def plate_stocks(plate_code: str = Query(..., description="如 US.MTKLIFE")):
    _require_enabled()
    df = futu_provider.get_plate_stock(plate_code)
    return {"plate_code": plate_code, "records": _df_to_records(df)}


# ─── 资金流 ───

@router.get("/capital/flow")
async def capital_flow(code: str = Query(..., description="如 US.AAPL")):
    _require_enabled()
    df = futu_provider.get_capital_flow(code)
    return {"code": code, "records": _df_to_records(df)}


@router.get("/capital/distribution")
async def capital_distribution(code: str = Query(..., description="如 US.AAPL")):
    _require_enabled()
    data = futu_provider.get_capital_distribution(code)
    return {"code": code, "data": data}


# ─── 交易账户（只查） ───

@router.get("/positions")
async def positions():
    """账户持仓（只读）。返回富途 SDK 原始字段。"""
    _require_enabled()
    df = futu_provider.get_positions()
    return {
        "trd_env": settings.futu_trd_env,
        "trd_market": settings.futu_trd_market,
        "records": _df_to_records(df),
    }


@router.get("/account")
async def account():
    """账户资金（只读）。返回富途 SDK 原始字段。"""
    _require_enabled()
    data = futu_provider.get_account_info()
    return {
        "trd_env": settings.futu_trd_env,
        "trd_market": settings.futu_trd_market,
        "data": data,
    }
