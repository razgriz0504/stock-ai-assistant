"""净 Gamma 敞口（Net GEX）API 路由。

数据源依赖富途 OpenD（只读）：
  - 期权链：futu_provider.get_option_chain_data（静态链 + 快照 merge）
  - 标的现价：futu_provider.get_snapshot
FUTU_ENABLED=false 时全部返回 503，前端菜单据此隐藏。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from app.auth import require_admin
from app.data.futu_provider import futu_provider
from app.gex.calculator import build_gex_report

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/gex",
    tags=["gex"],
    dependencies=[Depends(require_admin)],
)


def _require_enabled():
    if not settings.futu_enabled:
        raise HTTPException(status_code=503, detail="Futu disabled (FUTU_ENABLED=false)")


@router.get("/status")
def gex_status():
    """富途数据源状态（GEX 依赖项）。"""
    detail = futu_provider.status()
    return {"enabled": settings.futu_enabled, **detail}


@router.get("/analysis")
def gex_analysis(
    code: str = Query("US.AAPL", description="标的代码，如 US.AAPL / US.SPY"),
    max_expiries: int = Query(6, ge=1, le=12, description="纳入的最近到期日个数"),
    min_oi: int = Query(500, ge=0, description="OI 过滤阈值（剔除低流动性合约）"),
    r: float = Query(0.045, ge=0.0, le=0.2, description="无风险利率（年化）"),
):
    """Net GEX 分析：当前净敞口 + Zero Gamma + 按行权价/到期日聚合。"""
    _require_enabled()

    chain = futu_provider.get_option_chain_data(code, max_expiries=max_expiries)
    if chain is None or chain.empty:
        raise HTTPException(
            status_code=502,
            detail=f"期权链数据获取失败：请确认 OpenD 已连接、code={code} 存在期权且已订阅期权行情权限",
        )

    snap = futu_provider.get_snapshot((code,))
    if snap is None or snap.empty or "last_price" not in snap.columns:
        raise HTTPException(status_code=502, detail=f"标的快照获取失败：{code}")
    spot = float(snap.iloc[0]["last_price"])
    if not spot or spot <= 0:
        raise HTTPException(status_code=502, detail=f"标的现价无效：{spot}")

    report = build_gex_report(chain, spot, r=r, min_oi=min_oi, max_expiries=max_expiries)
    report["code"] = code
    return report
