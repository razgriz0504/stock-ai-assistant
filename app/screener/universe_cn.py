"""A 股股票池: 沪深300 + 中证500 并集 (~800 只), 24h 缓存.

数据源: akshare index_stock_cons_csindex
- 沪深300: 000300
- 中证500: 000905

过滤规则:
- 剔除 ST / *ST / 退（基本面地雷）
- 保留纯 6 位数字代码, 前缀 sh/sz 由 provider 层处理
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours
_cache: dict = {"symbols": [], "ts": 0.0, "names": {}}


def _fetch_index_cons(index_code: str) -> tuple[list[str], dict[str, str]]:
    """拉取指数成分股 (code, name_dict).

    akshare index_stock_cons_csindex 返回:
        日期 / 指数代码 / 指数名称 / 成分券代码 / 成分券名称 / 交易所
    """
    try:
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol=index_code)
        if df is None or df.empty:
            logger.warning(f"index_stock_cons_csindex({index_code}) returned empty")
            return [], {}

        # 兼容不同版本列名
        code_col = None
        name_col = None
        for c in df.columns:
            if "代码" in c and "指数" not in c:
                code_col = c
            elif "名称" in c and "指数" not in c:
                name_col = c
        if not code_col:
            logger.warning(f"cannot find code column in {df.columns.tolist()}")
            return [], {}

        codes = []
        names = {}
        for _, row in df.iterrows():
            code = str(row[code_col]).strip().zfill(6)
            name = str(row[name_col]).strip() if name_col else ""
            # 过滤 ST/*ST/退
            if "ST" in name.upper() or "退" in name:
                continue
            if len(code) == 6 and code.isdigit():
                codes.append(code)
                if name:
                    names[code] = name
        return codes, names

    except Exception as e:
        logger.error(f"fetch index {index_code} failed: {e}")
        return [], {}


def get_universe_cn(force_refresh: bool = False) -> list[str]:
    """获取 A 股股票池: 沪深300 + 中证500 并集 (24h 缓存).

    返回: 排序后的 6 位数字代码列表.
    """
    now = time.time()
    if not force_refresh and _cache["symbols"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["symbols"]

    logger.info("Fetching CN universe (CSI300 + CSI500)...")
    codes_300, names_300 = _fetch_index_cons("000300")
    codes_500, names_500 = _fetch_index_cons("000905")

    merged = sorted(set(codes_300) | set(codes_500))
    all_names = {**names_300, **names_500}

    if len(merged) < 100:
        logger.warning(f"CN universe too small ({len(merged)}), falling back to cache")
        if _cache["symbols"]:
            return _cache["symbols"]
        return merged  # 就算少也返回，避免死循环

    _cache["symbols"] = merged
    _cache["names"] = all_names
    _cache["ts"] = now
    logger.info(f"CN universe: {len(codes_300)} CSI300 + {len(codes_500)} CSI500 = {len(merged)} unique")
    return merged


def get_universe_cn_names() -> dict[str, str]:
    """获取股票池的 code → name 映射 (与 get_universe_cn 共用缓存)."""
    if not _cache["symbols"]:
        get_universe_cn()
    return _cache.get("names", {})
