"""板块强度雷达 REST API（前端 SPA: SectorStrengthPage.tsx）"""

import asyncio
import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.data.sector_strength import fetch_enhanced_sector_data
from app.data.sector_strength_cn import fetch_enhanced_sector_data_cn

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/sector-strength/data")
async def get_sector_strength_data(
    force_refresh: bool = Query(False),
    market: str = Query("us", regex="^(us|cn)$"),
):
    """返回增强板块数据 JSON，支持市场切换（us / cn）"""
    try:
        if market == "cn":
            data = await asyncio.to_thread(
                fetch_enhanced_sector_data_cn, use_cache=not force_refresh
            )
        else:
            data = await asyncio.to_thread(
                fetch_enhanced_sector_data, use_cache=not force_refresh
            )
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Sector strength data error (market={market}): {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)
