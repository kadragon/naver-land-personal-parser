from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sqlite3

from .models import Article


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS article (
    atcl_no        TEXT PRIMARY KEY,
    complex_no     TEXT,
    complex_name   TEXT,
    trade_type     TEXT,
    building_name  TEXT,
    floor_info     TEXT,
    price          TEXT,
    price_raw      INTEGER,
    supply_area    REAL,
    exclusive_area REAL,
    direction      TEXT,
    confirm_date   TEXT,
    agent_name     TEXT,
    article_desc   TEXT,
    raw_json       TEXT,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    is_active      INTEGER DEFAULT 1
);
"""


def _resolve_db_path(db_path: str) -> Path:
    return Path(db_path).expanduser()


def connect(db_path: str) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def upsert_article(conn: sqlite3.Connection, article: Article) -> None:
    payload = asdict(article)
    columns = ", ".join(payload.keys())
    placeholders = ", ".join([f":{key}" for key in payload.keys()])

    conn.execute(
        f"""
        INSERT INTO article ({columns})
        VALUES ({placeholders})
        ON CONFLICT(atcl_no) DO UPDATE SET
            complex_no = excluded.complex_no,
            complex_name = excluded.complex_name,
            trade_type = excluded.trade_type,
            building_name = excluded.building_name,
            floor_info = excluded.floor_info,
            price = excluded.price,
            price_raw = excluded.price_raw,
            supply_area = excluded.supply_area,
            exclusive_area = excluded.exclusive_area,
            direction = excluded.direction,
            confirm_date = excluded.confirm_date,
            agent_name = excluded.agent_name,
            article_desc = excluded.article_desc,
            raw_json = excluded.raw_json,
            last_seen_at = excluded.last_seen_at,
            is_active = 1
        """,
        payload,
    )


def _row_to_article(row: sqlite3.Row | None) -> Article | None:
    if row is None:
        return None
    return Article(
        atcl_no=row["atcl_no"],
        complex_no=row["complex_no"],
        complex_name=row["complex_name"],
        trade_type=row["trade_type"],
        building_name=row["building_name"],
        floor_info=row["floor_info"],
        price=row["price"],
        price_raw=row["price_raw"],
        supply_area=row["supply_area"],
        exclusive_area=row["exclusive_area"],
        direction=row["direction"],
        confirm_date=row["confirm_date"],
        agent_name=row["agent_name"],
        article_desc=row["article_desc"],
        raw_json=row["raw_json"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        is_active=row["is_active"],
    )


def list_articles(
    conn: sqlite3.Connection,
    include_inactive: bool = False,
    min_price: int | None = None,
    max_price: int | None = None,
) -> list[Article]:
    where = []
    params: list[int] = []

    if not include_inactive:
        where.append("is_active = 1")
    if min_price is not None:
        where.append("price_raw >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("price_raw <= ?")
        params.append(max_price)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    query = (
        "SELECT * FROM article "
        f"{where_sql} "
        "ORDER BY price_raw ASC, atcl_no ASC"
    )
    rows = conn.execute(query, params).fetchall()
    return [item for row in rows if (item := _row_to_article(row)) is not None]


def get_article(conn: sqlite3.Connection, atcl_no: str) -> Article | None:
    row = conn.execute("SELECT * FROM article WHERE atcl_no = ?", (atcl_no,)).fetchone()
    return _row_to_article(row)


def mark_inactive(conn: sqlite3.Connection, active_atcl_nos: set[str], now_utc: str) -> int:
    if not active_atcl_nos:
        cursor = conn.execute(
            "UPDATE article SET is_active = 0, last_seen_at = ? WHERE is_active = 1",
            (now_utc,),
        )
        return cursor.rowcount

    placeholders = ", ".join(["?"] * len(active_atcl_nos))
    query = (
        "UPDATE article "
        "SET is_active = 0, last_seen_at = ? "
        f"WHERE is_active = 1 AND atcl_no NOT IN ({placeholders})"
    )
    params: list[str] = [now_utc, *sorted(active_atcl_nos)]
    cursor = conn.execute(query, params)
    return cursor.rowcount


def get_stats(conn: sqlite3.Connection) -> dict[str, int | float | None]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_count,
            SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive_count,
            MIN(CASE WHEN is_active = 1 THEN price_raw END) AS min_price,
            MAX(CASE WHEN is_active = 1 THEN price_raw END) AS max_price,
            AVG(CASE WHEN is_active = 1 THEN price_raw END) AS avg_price
        FROM article
        """
    ).fetchone()

    return {
        "total_count": int(row["total_count"] or 0),
        "active_count": int(row["active_count"] or 0),
        "inactive_count": int(row["inactive_count"] or 0),
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "avg_price": row["avg_price"],
    }
