"""一次性数据迁移：将存量业务表记录归属到首个 admin 用户。

覆盖表：monitor_rules / backtest_records / user_preferences 的 user_id 字段。
仅回填 user_id IS NULL 的行；已有归属的行不动。

用法：
    python -m scripts.migrate_ownership --dry-run   # 只打印将要变更的行数
    python -m scripts.migrate_ownership             # 正式执行
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import text

from db.models import SessionLocal, User, engine

logger = logging.getLogger(__name__)

# (表名, 列名) —— 均为 user_id
TARGET_TABLES = [
    ("monitor_rules", "user_id"),
    ("backtest_records", "user_id"),
    ("user_preferences", "user_id"),
]


def _first_admin_id() -> int | None:
    db = SessionLocal()
    try:
        row = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
        return row.id if row else None
    finally:
        db.close()


def _count_null(table: str, col: str) -> int:
    with engine.connect() as conn:
        r = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"))
        return int(r.scalar() or 0)


def _update_null(table: str, col: str, admin_id: int) -> int:
    with engine.begin() as conn:
        r = conn.execute(
            text(f"UPDATE {table} SET {col} = :aid WHERE {col} IS NULL"),
            {"aid": admin_id},
        )
        return r.rowcount or 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate ownership of existing rows to the first admin.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts only; do not modify.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    admin_id = _first_admin_id()
    if admin_id is None:
        logger.error("No admin user found. Start the app once with INITIAL_ADMIN_PASSWORD to seed one.")
        return 2

    logger.info(f"Target admin user_id = {admin_id}")

    total_planned = 0
    for table, col in TARGET_TABLES:
        try:
            n = _count_null(table, col)
        except Exception as e:
            logger.warning(f"Skip {table}: {e}")
            continue
        total_planned += n
        logger.info(f"  {table}.{col}: {n} rows to backfill")

    if args.dry_run:
        logger.info(f"[dry-run] Total {total_planned} rows would be updated.")
        return 0

    if total_planned == 0:
        logger.info("Nothing to do.")
        return 0

    total_done = 0
    for table, col in TARGET_TABLES:
        try:
            n = _update_null(table, col, admin_id)
        except Exception as e:
            logger.warning(f"Skip {table}: {e}")
            continue
        total_done += n
        logger.info(f"  {table}.{col}: updated {n} rows")

    logger.info(f"Done. {total_done} rows migrated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
