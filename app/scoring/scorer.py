"""打分执行引擎 - 对关注列表中的股票逐一执行打分"""
import json
import logging

from db.models import SessionLocal, ScoringRun, ScoringResult
from app.data.yfinance_provider import YFinanceProvider
from app.backtest.sandbox import check_code_safety, run_user_strategy

logger = logging.getLogger(__name__)
_yf = YFinanceProvider()

RATING_MAP = [
    (90, "AA"),
    (80, "A"),
    (70, "B"),
    (60, "C"),
    (0, "D"),
]


def _auto_rating(score: float) -> str:
    for threshold, rating in RATING_MAP:
        if score >= threshold:
            return rating
    return "D"


def run_scoring(code: str, symbols: list, period: str = "1y",
                trigger: str = "manual") -> dict:
    """对多只股票执行打分，保存结果到 DB

    Returns:
        {"success": True, "run_id": N, "results": [...]}
        {"success": False, "error": "..."}
    """
    # 1. AST 安全检查
    is_safe, error_msg = check_code_safety(code, entry_func="score")
    if not is_safe:
        return {"success": False, "error": error_msg}

    if not symbols:
        return {"success": False, "error": "关注列表为空，请先在 /watchlist 添加股票"}

    db = SessionLocal()
    try:
        # 2. 计算版本号（自增）
        last_run = db.query(ScoringRun).order_by(ScoringRun.id.desc()).first()
        version = (last_run.version + 1) if last_run else 1

        # 3. 创建 ScoringRun 记录
        run = ScoringRun(
            version=version,
            code=code,
            period=period,
            trigger=trigger,
            stock_count=len(symbols),
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        # 4. 对每只股票逐一执行打分
        results = []
        for symbol in symbols:
            result_data = _score_single(code, symbol, period, run_id, db)
            results.append(result_data)

        # 5. 更新 run 状态
        run.status = "completed"
        db.commit()

        # 按 score 降序排序（error 的排最后）
        results.sort(key=lambda x: x.get("score") if x.get("score") is not None else -1,
                     reverse=True)

        return {"success": True, "run_id": run_id, "version": version, "results": results}

    except Exception as e:
        logger.error(f"Scoring run failed: {e}", exc_info=True)
        try:
            if 'run' in locals():
                run.status = "failed"
                db.commit()
        except Exception:
            pass
        return {"success": False, "error": f"打分执行失败: {str(e)}"}
    finally:
        db.close()


def _score_single(code: str, symbol: str, period: str,
                  run_id: int, db) -> dict:
    """对单只股票执行打分"""
    try:
        # 获取历史数据
        df = _yf.get_history(symbol, period)
        if df.empty:
            error_msg = f"无法获取 {symbol} 的历史数据"
            _save_result(db, run_id, symbol, error=error_msg)
            return {"symbol": symbol, "error": error_msg}

        # 准备 DataFrame（与 F1 一致格式）
        sandbox_df = df.copy()
        sandbox_df['Date'] = sandbox_df.index.strftime('%Y-%m-%d')
        sandbox_df = sandbox_df.reset_index(drop=True)
        sandbox_df = sandbox_df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]

        # 沙箱执行 score(data)
        sandbox_result = run_user_strategy(
            code, sandbox_df, timeout=30,
            entry_func="score", output_mode="dict"
        )
        if not sandbox_result["success"]:
            _save_result(db, run_id, symbol, error=sandbox_result["error"])
            return {"symbol": symbol, "error": sandbox_result["error"]}

        score_data = sandbox_result["result"]
        score_val = float(score_data.get("score", 0))
        rating = score_data.get("rating") or _auto_rating(score_val)
        details = score_data.get("details", {})

        # 获取实时报价
        quote = _yf.get_realtime_quote(symbol)
        price = quote.price if quote else None
        change_pct = quote.change_pct if quote else None

        # 保存结果到 DB
        _save_result(db, run_id, symbol,
                     score=score_val, rating=rating,
                     price=price, change_pct=change_pct,
                     details=details)

        return {
            "symbol": symbol,
            "score": score_val,
            "rating": rating,
            "price": price,
            "change_pct": change_pct,
            "details": details,
        }

    except Exception as e:
        error_msg = f"{symbol} 打分异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        _save_result(db, run_id, symbol, error=error_msg)
        return {"symbol": symbol, "error": error_msg}


def _save_result(db, run_id: int, symbol: str, score=None, rating="",
                 price=None, change_pct=None, details=None, error=""):
    """保存单只股票的打分结果"""
    result = ScoringResult(
        run_id=run_id,
        symbol=symbol,
        score=score,
        rating=rating,
        price=price,
        change_pct=change_pct,
        details_json=json.dumps(details, ensure_ascii=False) if details else "",
        error=error,
    )
    db.add(result)
    db.commit()
