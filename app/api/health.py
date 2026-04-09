"""健康检查端点"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "stock-ai-assistant"}
