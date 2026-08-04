"""富途 OpenD 只读数据源封装。

设计约束（严禁违反）：
  1. 本文件**只**封装查询类方法。禁止导入或调用 place_order / modify_order /
     cancel_order / unlock_trade 等交易变更方法。
  2. trade_ctx 仅用于 position_list_query / accinfo_query，永远不传交易密码。
  3. 单例 + 懒加载 + 每次调用内部捕获异常返回空结果，避免 OpenD 未启动/掉线时
     拖垮整个 FastAPI 服务。
  4. 加 TTL 缓存，避免高频调用打爆 OpenD 限频。

启用方式：环境变量 FUTU_ENABLED=true，且服务器上 OpenD 已启动并完成登录。
"""
from __future__ import annotations

import logging
import time
import threading
from typing import Any, Callable, Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


# ─── TTL 缓存装饰器（简易，进程内） ───
def _ttl_cache(ttl: float) -> Callable:
    def decorator(func: Callable) -> Callable:
        cache: dict[tuple, tuple[float, Any]] = {}
        lock = threading.Lock()

        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            with lock:
                hit = cache.get(key)
                if hit and now - hit[0] < ttl:
                    return hit[1]
            result = func(*args, **kwargs)
            with lock:
                cache[key] = (now, result)
            return result

        wrapper.__name__ = func.__name__  # type: ignore[attr-defined]
        return wrapper

    return decorator


class FutuProvider:
    """单例只读数据源。"""

    _instance: Optional["FutuProvider"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._quote = None       # OpenQuoteContext
                cls._instance._trade = None       # OpenSecTradeContext
                cls._instance._sdk_available = None  # 三态：None 未探测 / True / False
            return cls._instance

    # ─── SDK 探测 ───
    def _ensure_sdk(self) -> bool:
        if self._sdk_available is not None:
            return self._sdk_available
        try:
            import futu  # noqa: F401
            self._sdk_available = True
        except Exception as e:
            logger.warning(f"[futu] futu-api SDK 未安装或导入失败：{e}")
            self._sdk_available = False
        return self._sdk_available

    # ─── 上下文获取 ───
    def _get_quote(self):
        if not settings.futu_enabled:
            return None
        if not self._ensure_sdk():
            return None
        if self._quote is not None:
            return self._quote
        try:
            from futu import OpenQuoteContext
            self._quote = OpenQuoteContext(
                host=settings.futu_opend_host,
                port=settings.futu_opend_port,
            )
            logger.info(
                f"[futu] OpenQuoteContext 连接建立 "
                f"{settings.futu_opend_host}:{settings.futu_opend_port}"
            )
        except Exception as e:
            logger.warning(f"[futu] OpenQuoteContext 连接失败：{e}")
            self._quote = None
        return self._quote

    def _get_trade(self):
        if not settings.futu_enabled:
            return None
        if not self._ensure_sdk():
            return None
        if self._trade is not None:
            return self._trade
        try:
            from futu import OpenSecTradeContext, TrdMarket, SecurityFirm
            market = getattr(TrdMarket, settings.futu_trd_market.upper(), TrdMarket.US)
            self._trade = OpenSecTradeContext(
                filter_trdmarket=market,
                host=settings.futu_opend_host,
                port=settings.futu_opend_port,
                security_firm=SecurityFirm.FUTUSECURITIES,
            )
            logger.info(f"[futu] OpenSecTradeContext 连接建立 market={market}")
        except Exception as e:
            logger.warning(f"[futu] OpenSecTradeContext 连接失败：{e}")
            self._trade = None
        return self._trade

    def _trd_env(self):
        try:
            from futu import TrdEnv
            return getattr(TrdEnv, settings.futu_trd_env.upper(), TrdEnv.SIMULATE)
        except Exception:
            return None

    # ─── 状态 ───
    def status(self) -> dict:
        if not settings.futu_enabled:
            return {"connected": False, "reason": "FUTU_ENABLED=false"}
        if not self._ensure_sdk():
            return {"connected": False, "reason": "futu-api SDK 未安装"}
        q = self._get_quote()
        if q is None:
            return {"connected": False, "reason": "OpenD 未连接"}
        try:
            from futu import RET_OK
            ret, data = q.get_global_state()
            if ret == RET_OK:
                return {
                    "connected": True,
                    "market_us": data.get("market_us"),
                    "market_hk": data.get("market_hk"),
                    "market_sh": data.get("market_sh"),
                    "server_ver": data.get("server_ver"),
                    "trd_logined": data.get("trd_logined"),
                    "qot_logined": data.get("qot_logined"),
                    "program_status_type": data.get("program_status_type"),
                }
            return {"connected": False, "reason": f"get_global_state 返回：{data}"}
        except Exception as e:
            return {"connected": False, "reason": f"探测异常：{e}"}

    # ─── 行情：快照 ───
    @_ttl_cache(ttl=5.0)
    def get_snapshot(self, codes_tuple: tuple[str, ...]) -> pd.DataFrame:
        """codes 用 tuple 传入以配合缓存；使用方封装 list -> tuple。"""
        q = self._get_quote()
        if q is None or not codes_tuple:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = q.get_market_snapshot(list(codes_tuple))
            if ret != RET_OK:
                logger.warning(f"[futu] get_market_snapshot 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_snapshot 异常：{e}")
            return pd.DataFrame()

    # ─── 行情：买卖盘 ───
    @_ttl_cache(ttl=3.0)
    def get_order_book(self, code: str, num: int = 10) -> dict:
        q = self._get_quote()
        if q is None or not code:
            return {}
        try:
            from futu import RET_OK
            ret, data = q.get_order_book(code, num=num)
            if ret != RET_OK:
                logger.warning(f"[futu] get_order_book 失败：{data}")
                return {}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[futu] get_order_book 异常：{e}")
            return {}

    # ─── 行情：逐笔 ───
    @_ttl_cache(ttl=3.0)
    def get_rt_ticker(self, code: str, num: int = 100) -> pd.DataFrame:
        q = self._get_quote()
        if q is None or not code:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = q.get_rt_ticker(code, num=num)
            if ret != RET_OK:
                logger.warning(f"[futu] get_rt_ticker 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_rt_ticker 异常：{e}")
            return pd.DataFrame()

    # ─── 行情：K线 ───
    @_ttl_cache(ttl=60.0)
    def get_kline(
        self,
        code: str,
        ktype: str = "K_DAY",
        start: str = "",
        end: str = "",
        max_count: int = 1000,
    ) -> pd.DataFrame:
        q = self._get_quote()
        if q is None or not code:
            return pd.DataFrame()
        try:
            from futu import RET_OK, KLType, AuType
            k_enum = getattr(KLType, ktype, KLType.K_DAY)
            ret, data, _page_req_key = q.request_history_kline(
                code,
                start=start or None,
                end=end or None,
                ktype=k_enum,
                autype=AuType.QFQ,
                max_count=max_count,
            )
            if ret != RET_OK:
                logger.warning(f"[futu] request_history_kline 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_kline 异常：{e}")
            return pd.DataFrame()

    # ─── 行情：分时 ───
    @_ttl_cache(ttl=5.0)
    def get_rt_data(self, code: str) -> pd.DataFrame:
        q = self._get_quote()
        if q is None or not code:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = q.get_rt_data(code)
            if ret != RET_OK:
                logger.warning(f"[futu] get_rt_data 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_rt_data 异常：{e}")
            return pd.DataFrame()

    # ─── 期权：静态链 + 快照 merge（Net GEX 计算用） ───
    @_ttl_cache(ttl=60.0)
    def get_option_chain_data(self, code: str, max_expiries: int = 6) -> pd.DataFrame:
        """期权链静态信息 + 行情快照合并。

        Futu get_option_chain 仅返回静态信息（code/lot_size/option_type/
        strike_time/strike_price 等），不含 last_price 与 open_interest；
        因此用返回的期权代码批量调 get_market_snapshot 补齐行情后 merge。
        返回列：code/expire_date/strike_price/option_type/lot_size/
        last_price/open_interest/iv_snap。
        """
        q = self._get_quote()
        if q is None or not code:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, expiries = q.get_option_expiration_date(code)
            if ret != RET_OK or expiries is None:
                logger.warning(f"[futu] get_option_expiration_date 失败：{expiries}")
                return pd.DataFrame()

            # 富途返回 DataFrame（列 strike_time），兼容 list 兜底
            if isinstance(expiries, pd.DataFrame):
                if expiries.empty or "strike_time" not in expiries.columns:
                    logger.warning("[futu] get_option_expiration_date 无 strike_time 列")
                    return pd.DataFrame()
                exp_list = [str(e) for e in expiries["strike_time"]]
            else:
                exp_list = [str(e) for e in expiries]

            frames = []
            for exp in sorted(exp_list)[:max_expiries]:
                # option_type 缺省 = ALL，一次拿回 Call + Put
                ret, chain_df = q.get_option_chain(code, start=exp, end=exp)
                if ret == RET_OK and isinstance(chain_df, pd.DataFrame) and not chain_df.empty:
                    frames.append(chain_df)
                elif ret != RET_OK:
                    logger.warning(f"[futu] get_option_chain 失败 {exp}：{chain_df}")
            if not frames:
                return pd.DataFrame()
            static_df = pd.concat(frames, ignore_index=True)

            # 批量快照（单次上限 400 只，分片）
            codes = static_df["code"].tolist()
            snap_parts = []
            for i in range(0, len(codes), 400):
                ret, snap_df = q.get_market_snapshot(codes[i:i + 400])
                if ret != RET_OK:
                    logger.warning(f"[futu] 期权快照失败：{snap_df}")
                    continue
                snap_parts.append(snap_df)
            if not snap_parts:
                return pd.DataFrame()
            snap_df = pd.concat(snap_parts, ignore_index=True)

            # 只挑快照所需列 merge，避免 name/option_type/strike_time 重叠列生成 _x/_y
            snap_cols = [c for c in (
                "code", "last_price", "option_open_interest",
                "option_implied_volatility",
            ) if c in snap_df.columns]
            merged = pd.merge(static_df, snap_df[snap_cols], on="code", how="inner")

            # 到期日字段名统一（富途静态链实际字段为 strike_time，yyyy-MM-dd）
            if "expire_date" not in merged.columns and "strike_time" in merged.columns:
                merged.rename(columns={"strike_time": "expire_date"}, inplace=True)
            merged.rename(columns={
                "option_open_interest": "open_interest",
                "option_implied_volatility": "iv_snap",
            }, inplace=True)
            return merged
        except Exception as e:
            logger.warning(f"[futu] get_option_chain_data 异常：{e}")
            return pd.DataFrame()

    # ─── 板块：列表 ───
    @_ttl_cache(ttl=300.0)
    def get_plate_list(self, market: str = "US", plate_class: str = "INDUSTRY") -> pd.DataFrame:
        q = self._get_quote()
        if q is None:
            return pd.DataFrame()
        try:
            from futu import RET_OK, Market, Plate
            m_enum = getattr(Market, market.upper(), Market.US)
            c_enum = getattr(Plate, plate_class.upper(), Plate.INDUSTRY)
            ret, data = q.get_plate_list(m_enum, c_enum)
            if ret != RET_OK:
                logger.warning(f"[futu] get_plate_list 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_plate_list 异常：{e}")
            return pd.DataFrame()

    # ─── 板块：成分股 ───
    @_ttl_cache(ttl=300.0)
    def get_plate_stock(self, plate_code: str) -> pd.DataFrame:
        q = self._get_quote()
        if q is None or not plate_code:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = q.get_plate_stock(plate_code)
            if ret != RET_OK:
                logger.warning(f"[futu] get_plate_stock 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_plate_stock 异常：{e}")
            return pd.DataFrame()

    # ─── 资金流向 ───
    @_ttl_cache(ttl=30.0)
    def get_capital_flow(self, code: str) -> pd.DataFrame:
        q = self._get_quote()
        if q is None or not code:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = q.get_capital_flow(code)
            if ret != RET_OK:
                logger.warning(f"[futu] get_capital_flow 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_capital_flow 异常：{e}")
            return pd.DataFrame()

    # ─── 资金分布（大中小单） ───
    @_ttl_cache(ttl=30.0)
    def get_capital_distribution(self, code: str) -> dict:
        q = self._get_quote()
        if q is None or not code:
            return {}
        try:
            from futu import RET_OK
            ret, data = q.get_capital_distribution(code)
            if ret != RET_OK:
                logger.warning(f"[futu] get_capital_distribution 失败：{data}")
                return {}
            # SDK 返回 DataFrame，取第一行转 dict
            if isinstance(data, pd.DataFrame) and not data.empty:
                return data.iloc[0].to_dict()
            if isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            logger.warning(f"[futu] get_capital_distribution 异常：{e}")
            return {}

    # ─── 交易：持仓（只查，不改） ───
    @_ttl_cache(ttl=15.0)
    def get_positions(self) -> pd.DataFrame:
        t = self._get_trade()
        env = self._trd_env()
        if t is None or env is None:
            return pd.DataFrame()
        try:
            from futu import RET_OK
            ret, data = t.position_list_query(trd_env=env)
            if ret != RET_OK:
                logger.warning(f"[futu] position_list_query 失败：{data}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.warning(f"[futu] get_positions 异常：{e}")
            return pd.DataFrame()

    # ─── 交易：账户资金（只查，不改） ───
    @_ttl_cache(ttl=15.0)
    def get_account_info(self) -> dict:
        t = self._get_trade()
        env = self._trd_env()
        if t is None or env is None:
            return {}
        try:
            from futu import RET_OK
            ret, data = t.accinfo_query(trd_env=env)
            if ret != RET_OK:
                logger.warning(f"[futu] accinfo_query 失败：{data}")
                return {}
            if isinstance(data, pd.DataFrame) and not data.empty:
                return data.iloc[0].to_dict()
            if isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            logger.warning(f"[futu] get_account_info 异常：{e}")
            return {}


# 全局单例
futu_provider = FutuProvider()
