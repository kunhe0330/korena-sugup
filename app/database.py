"""SQLite DB 모듈 — supply_demand_daily 테이블 관리."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS supply_demand_daily (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at      TEXT NOT NULL,
    biz_date          TEXT NOT NULL,
    market            TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    name              TEXT NOT NULL,
    sector            TEXT,
    sector_group      TEXT,
    price             INTEGER,
    price_change_pct  REAL,
    frgn_net_qty      INTEGER DEFAULT 0,
    orgn_net_qty      INTEGER DEFAULT 0,
    frgn_net_amt      INTEGER DEFAULT 0,
    orgn_net_amt      INTEGER DEFAULT 0,
    acml_vol          INTEGER DEFAULT 0,
    UNIQUE(biz_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_sd_date ON supply_demand_daily(biz_date);
CREATE INDEX IF NOT EXISTS idx_sd_ticker ON supply_demand_daily(ticker);
CREATE INDEX IF NOT EXISTS idx_sd_sector ON supply_demand_daily(sector_group);
"""


def init_db(db_path: str | None = None) -> None:
    """DB 초기화 — 테이블이 없으면 생성."""
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    logger.info("DB 초기화 완료: %s", path)


@contextmanager
def get_conn(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """DB 커넥션 컨텍스트 매니저. Row factory 적용."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def upsert_supply_demand_records(records: list[dict]) -> int:
    """수급 데이터 UPSERT — (biz_date, ticker)가 같으면 업데이트."""
    if not records:
        return 0

    sql = """
        INSERT INTO supply_demand_daily (
            collected_at, biz_date, market, ticker, name,
            sector, sector_group, price, price_change_pct,
            frgn_net_qty, orgn_net_qty, frgn_net_amt, orgn_net_amt, acml_vol
        )
        VALUES (
            :collected_at, :biz_date, :market, :ticker, :name,
            :sector, :sector_group, :price, :price_change_pct,
            :frgn_net_qty, :orgn_net_qty, :frgn_net_amt, :orgn_net_amt, :acml_vol
        )
        ON CONFLICT(biz_date, ticker) DO UPDATE SET
            collected_at     = excluded.collected_at,
            market           = excluded.market,
            name             = excluded.name,
            sector           = excluded.sector,
            sector_group     = excluded.sector_group,
            price            = excluded.price,
            price_change_pct = excluded.price_change_pct,
            frgn_net_qty     = excluded.frgn_net_qty,
            orgn_net_qty     = excluded.orgn_net_qty,
            frgn_net_amt     = excluded.frgn_net_amt,
            orgn_net_amt     = excluded.orgn_net_amt,
            acml_vol         = excluded.acml_vol
    """

    with get_conn() as conn:
        conn.executemany(sql, records)
        conn.commit()
        return conn.total_changes


def get_last_collection_date() -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(collected_at) AS ts FROM supply_demand_daily"
        ).fetchone()
        return row["ts"] if row and row["ts"] else None


def get_total_record_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM supply_demand_daily").fetchone()
        return row["c"] if row else 0


def get_collected_day_count() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT biz_date) AS c FROM supply_demand_daily"
        ).fetchone()
        return row["c"] if row else 0
