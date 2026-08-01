"""市场环境（红绿灯）REST API（前端 SPA: MarketPage.tsx）"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.market.regime import (
    compute_market_snapshot, get_latest_snapshot, get_regime_history,
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

# 防止并发重复计算
_refresh_lock = asyncio.Lock()


@router.get("/api/market/regime")
async def market_regime():
    """获取最近一次市场环境快照（不触发计算）"""
    snap = get_latest_snapshot()
    if not snap:
        return {"snapshot": None, "message": "暂无快照，请先刷新"}
    return {"snapshot": snap}


@router.post("/api/market/regime/refresh")
async def market_regime_refresh(include_breadth: bool = Query(True)):
    """立即重算市场环境快照（含全 Universe 宽度时耗时约 1-2 分钟）"""
    if _refresh_lock.locked():
        raise HTTPException(status_code=409, detail="已有刷新任务在执行中")
    async with _refresh_lock:
        try:
            snap = await asyncio.to_thread(compute_market_snapshot, include_breadth)
        except Exception as e:
            logger.error(f"[market] refresh failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"计算失败: {e}")
    return {"snapshot": snap}


@router.get("/api/market/regime/history")
async def market_regime_history(days: int = Query(120, ge=7, le=365)):
    """红绿灯与宽度历史序列"""
    return {"history": get_regime_history(days)}
