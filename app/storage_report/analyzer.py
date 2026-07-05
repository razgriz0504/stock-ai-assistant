"""存储行业研究报告 - 业务逻辑（六大能力的 LLM 调用与结果聚合）

数据源统一为 Gemini 联网搜索：chat(..., web_search=True)。
结构化能力（景气度/价格趋势/异动）要求 LLM 输出 JSON，用 _extract_json 容错解析。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.client import chat, get_model
from db.models import StorageReport, StorageReportConfig
from app.storage_report.constants import CATEGORIES, THEMES, VENDORS, get_metric
from app.storage_report.prompts import (
    DEFAULT_METRIC_PROMPT,
    DEFAULT_PROSPERITY_PROMPT,
    DEFAULT_PRICE_TREND_PROMPT,
    DEFAULT_SUPPLY_DEMAND_PROMPT,
    DEFAULT_VENDOR_PROMPT,
    DEFAULT_ANOMALY_PROMPT,
)

logger = logging.getLogger(__name__)


# ─── JSON 容错解析（对齐 x_monitor/processor.py）───

def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _strip_citations(s: str) -> str:
    """移除联网 grounding 引用角标，避免其插入 JSON 结构缝隙导致解析失败。
    覆盖 [1](url) markdown 链接式与 [1] / [1, 2] 纯方括号式。"""
    s = re.sub(r"\s*\[\d+\]\([^)]*\)", "", s)
    s = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]", "", s)
    return s


def _extract_json(s: str) -> dict | None:
    """容错地从 LLM 输出中抽取 JSON 对象"""
    s = _strip_code_fence(s)
    s = _strip_citations(s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", s, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ─── 配置与版本 ───

def get_or_create_storage_config(db: Session) -> StorageReportConfig:
    """获取或创建单例配置行（id=1）"""
    config = db.query(StorageReportConfig).filter_by(id=1).first()
    if not config:
        config = StorageReportConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _get_next_version(db: Session) -> int:
    last = db.query(StorageReport).order_by(StorageReport.version.desc()).first()
    return (last.version + 1) if last and last.version else 1


def resolve_prompts(config: StorageReportConfig) -> dict:
    """将 config 中的自定义 prompt 与默认 prompt 合并，返回各能力最终 prompt"""
    return {
        "metric": (config.default_metric_system_prompt or "").strip() or DEFAULT_METRIC_PROMPT,
        "prosperity": (config.default_prosperity_system_prompt or "").strip() or DEFAULT_PROSPERITY_PROMPT,
        "price_trend": (config.default_price_trend_system_prompt or "").strip() or DEFAULT_PRICE_TREND_PROMPT,
        "supply_demand": (config.default_supply_demand_system_prompt or "").strip() or DEFAULT_SUPPLY_DEMAND_PROMPT,
        "vendor": (config.default_vendor_system_prompt or "").strip() or DEFAULT_VENDOR_PROMPT,
        "anomaly": (config.default_anomaly_system_prompt or "").strip() or DEFAULT_ANOMALY_PROMPT,
    }


def _cat_label(cat: str) -> str:
    return CATEGORIES.get(cat, cat)


# ─── 六大能力 ───

async def query_metric(metric_key: str, category: str = "", prompt: Optional[str] = None) -> dict:
    """指标查询与口径解释"""
    metric = get_metric(metric_key)
    sys_prompt = (prompt or "").strip() or DEFAULT_METRIC_PROMPT
    if metric:
        user_prompt = (
            f"指标：{metric['name']}（单位：{metric['unit']}）\n"
            f"已知口径：{metric['definition']}\n"
            f"常见发布机构：{metric['source_hint']}\n"
            f"品类：{_cat_label(category) if category else '通用'}\n"
            f"请解释口径并联网检索该指标的最新数值与近期变化。"
        )
    else:
        user_prompt = (
            f"指标：{metric_key}\n品类：{_cat_label(category) if category else '通用'}\n"
            f"请解释该存储行业指标的口径，并联网检索其最新数值与近期变化。"
        )
    try:
        content = await chat(user_prompt, system_prompt=sys_prompt, web_search=True)
    except Exception as e:
        logger.error(f"query_metric failed: {e}")
        content = "AI 分析暂不可用"
    return {
        "metric_key": metric_key,
        "metric_name": metric["name"] if metric else metric_key,
        "category": category,
        "content": content,
    }


async def analyze_prosperity(
    time_range: str,
    categories: list[str],
    themes: list[str],
    prompt: Optional[str] = None,
) -> dict:
    """行业景气度综合研判（结构化 JSON）"""
    sys_prompt = (prompt or "").strip() or DEFAULT_PROSPERITY_PROMPT
    cats = categories or list(CATEGORIES.keys())
    thms = themes or list(THEMES.keys())
    theme_labels = {t: THEMES.get(t, t) for t in thms}
    user_prompt = json.dumps(
        {
            "time_range": time_range,
            "categories": cats,
            "themes": theme_labels,
        },
        ensure_ascii=False,
    )
    try:
        raw = await chat(user_prompt, system_prompt=sys_prompt, web_search=True, inline_citations=False)
    except Exception as e:
        logger.error(f"analyze_prosperity failed: {e}")
        return {"error": "AI 分析暂不可用", "raw": ""}
    parsed = _extract_json(raw)
    if parsed is None:
        return {"raw": raw}
    parsed["raw"] = raw
    return parsed


async def analyze_price_trend(
    categories: list[str],
    time_range: str,
    prompt: Optional[str] = None,
) -> dict:
    """价格趋势分析（结构化 JSON）"""
    sys_prompt = (prompt or "").strip() or DEFAULT_PRICE_TREND_PROMPT
    cats = categories or list(CATEGORIES.keys())
    user_prompt = json.dumps(
        {"time_range": time_range, "categories": cats},
        ensure_ascii=False,
    )
    try:
        raw = await chat(user_prompt, system_prompt=sys_prompt, web_search=True, inline_citations=False)
    except Exception as e:
        logger.error(f"analyze_price_trend failed: {e}")
        return {"error": "AI 分析暂不可用", "raw": ""}
    parsed = _extract_json(raw)
    if parsed is None:
        return {"raw": raw}
    parsed["raw"] = raw
    return parsed


async def analyze_supply_demand(
    category: str,
    time_range: str,
    prompt: Optional[str] = None,
) -> str:
    """供需归因分析（Markdown 叙事）"""
    sys_prompt = (prompt or "").strip() or DEFAULT_SUPPLY_DEMAND_PROMPT
    user_prompt = (
        f"品类：{_cat_label(category)}\n时间范围：{time_range}\n"
        f"请做供需归因分析。"
    )
    try:
        return await chat(user_prompt, system_prompt=sys_prompt, web_search=True)
    except Exception as e:
        logger.error(f"analyze_supply_demand failed: {e}")
        return "AI 分析暂不可用"


async def track_vendors(vendors: list[str], prompt: Optional[str] = None) -> str:
    """厂商动态追踪（Markdown 叙事）"""
    sys_prompt = (prompt or "").strip() or DEFAULT_VENDOR_PROMPT
    vs = vendors or list(VENDORS.keys())
    labels = [f"{v}（{VENDORS.get(v, v)}）" for v in vs]
    user_prompt = "请追踪以下存储厂商的最新动态：\n" + "、".join(labels)
    try:
        return await chat(user_prompt, system_prompt=sys_prompt, web_search=True)
    except Exception as e:
        logger.error(f"track_vendors failed: {e}")
        return "AI 分析暂不可用"


async def detect_anomaly(time_range: str, prompt: Optional[str] = None) -> dict:
    """景气度异动识别（结构化 JSON）"""
    sys_prompt = (prompt or "").strip() or DEFAULT_ANOMALY_PROMPT
    user_prompt = f"时间范围：{time_range}\n请识别存储行业景气度异动信号。"
    try:
        raw = await chat(user_prompt, system_prompt=sys_prompt, web_search=True, inline_citations=False)
    except Exception as e:
        logger.error(f"detect_anomaly failed: {e}")
        return {"error": "AI 分析暂不可用", "raw": ""}
    parsed = _extract_json(raw)
    if parsed is None:
        return {"raw": raw}
    parsed["raw"] = raw
    return parsed


# ─── 完整报告聚合 ───

async def generate_full_report(
    db: Session,
    categories: Optional[list[str]] = None,
    time_range: str = "近3个月",
    trigger: str = "manual",
    report_id: Optional[int] = None,
) -> dict:
    """并发生成完整版本化报告并落库。

    若传入 report_id 则复用已创建的行（供后台任务先建行后填充），否则新建。
    """
    config = get_or_create_storage_config(db)
    prompts = resolve_prompts(config)
    cats = categories or json.loads(config.default_categories or '["DRAM","NAND","HBM"]')
    model_name = get_model()

    if report_id is not None:
        report = db.query(StorageReport).filter_by(id=report_id).first()
        if not report:
            return {"error": "Report not found"}
    else:
        report = StorageReport(
            version=_get_next_version(db),
            report_date=datetime.now(timezone.utc),
            status="running",
            trigger=trigger,
            model_name=model_name,
            categories=json.dumps(cats, ensure_ascii=False),
            time_range=time_range,
            prosperity_system_prompt=prompts["prosperity"],
            price_trend_system_prompt=prompts["price_trend"],
            supply_demand_system_prompt=prompts["supply_demand"],
            vendor_system_prompt=prompts["vendor"],
            anomaly_system_prompt=prompts["anomaly"],
        )
        db.add(report)
        db.commit()
        db.refresh(report)

    try:
        # 供需归因逐品类做，控制并发规模用 gather 整体调度
        prosperity, price_trend, vendor, anomaly = await asyncio.gather(
            analyze_prosperity(time_range, cats, list(THEMES.keys()), prompt=prompts["prosperity"]),
            analyze_price_trend(cats, time_range, prompt=prompts["price_trend"]),
            track_vendors(list(VENDORS.keys()), prompt=prompts["vendor"]),
            detect_anomaly(time_range, prompt=prompts["anomaly"]),
        )
        # 供需归因：以首个品类为代表（完整报告聚合层面）
        primary_cat = cats[0] if cats else "DRAM"
        supply_demand = await analyze_supply_demand(
            primary_cat, time_range, prompt=prompts["supply_demand"]
        )

        report.prosperity_data = json.dumps(prosperity, ensure_ascii=False)
        report.price_trend_data = json.dumps(price_trend, ensure_ascii=False)
        report.supply_demand_data = supply_demand
        report.vendor_data = vendor
        report.anomaly_data = json.dumps(anomaly, ensure_ascii=False)
        report.status = "completed"
        db.commit()
        logger.info(f"Storage report v{report.version} (id={report.id}) generated")
        return {"report_id": report.id, "version": report.version, "status": "completed"}
    except Exception as e:
        logger.error(f"generate_full_report failed (id={report.id}): {e}", exc_info=True)
        try:
            report.status = "failed"
            report.error_message = str(e)
            db.commit()
        except Exception:
            pass
        return {"report_id": report.id, "version": report.version, "status": "failed", "error": str(e)}
