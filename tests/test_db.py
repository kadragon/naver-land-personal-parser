from __future__ import annotations

from pathlib import Path

from nland.db import (
    connect,
    get_article,
    get_last_fetched_at,
    get_stats,
    init_db,
    list_articles,
    mark_inactive,
    set_last_fetched_at,
    upsert_article,
)
from tests.factories import make_article


def test_init_db_creates_article_table(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"

    init_db(str(db_path))

    with connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='article'"
        ).fetchone()
        columns = conn.execute("PRAGMA table_info(article)").fetchall()
    assert row["name"] == "article"
    column_names = {item["name"] for item in columns}
    assert {"tag_list", "cp_name", "latitude", "longitude", "rep_img_url"} <= column_names


def test_init_db_adds_missing_extended_columns_to_existing_table(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    with connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE article (
                atcl_no TEXT PRIMARY KEY,
                complex_no TEXT,
                complex_name TEXT,
                trade_type TEXT,
                building_name TEXT,
                floor_info TEXT,
                price TEXT,
                price_raw INTEGER,
                supply_area REAL,
                exclusive_area REAL,
                direction TEXT,
                confirm_date TEXT,
                agent_name TEXT,
                article_desc TEXT,
                raw_json TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
            """
        )
        conn.commit()

    init_db(str(db_path))

    with connect(str(db_path)) as conn:
        columns = conn.execute("PRAGMA table_info(article)").fetchall()
    column_names = {item["name"] for item in columns}
    assert {"tag_list", "cp_name", "latitude", "longitude", "rep_img_url"} <= column_names


def test_upsert_insert_and_update_preserves_first_seen(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    init_db(str(db_path))

    first = make_article("1", 45000, "2026-02-22T00:00:00Z")
    second = make_article("1", 47000, "2026-02-23T00:00:00Z")

    with connect(str(db_path)) as conn:
        upsert_article(conn, first)
        conn.commit()

        upsert_article(conn, second)
        conn.commit()

        saved = get_article(conn, "1")

    assert saved is not None
    assert saved.first_seen_at == "2026-02-22T00:00:00Z"
    assert saved.last_seen_at == "2026-02-23T00:00:00Z"
    assert saved.price_raw == 47000
    assert saved.is_active == 1


def test_list_articles_filters_by_active_and_price_range(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    init_db(str(db_path))

    a1 = make_article("1", 40000, "2026-02-22T00:00:00Z", is_active=1)
    a2 = make_article("2", 70000, "2026-02-22T00:00:00Z", is_active=0)
    a3 = make_article("3", 80000, "2026-02-22T00:00:00Z", is_active=1)

    with connect(str(db_path)) as conn:
        for article in (a1, a2, a3):
            upsert_article(conn, article)
        conn.execute("UPDATE article SET is_active = 0 WHERE atcl_no = '2'")
        conn.commit()

        active_only = list_articles(conn)
        all_rows = list_articles(conn, include_inactive=True)
        filtered = list_articles(conn, include_inactive=True, min_price=50000, max_price=80000)

    assert [item.atcl_no for item in active_only] == ["1", "3"]
    assert [item.atcl_no for item in all_rows] == ["1", "2", "3"]
    assert [item.atcl_no for item in filtered] == ["2", "3"]


def test_mark_inactive_marks_only_missing_active_items(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    init_db(str(db_path))

    with connect(str(db_path)) as conn:
        upsert_article(conn, make_article("1", 40000, "2026-02-22T00:00:00Z"))
        upsert_article(conn, make_article("2", 50000, "2026-02-22T00:00:00Z"))
        conn.commit()

        changed = mark_inactive(conn, {"1"}, "2026-02-23T00:00:00Z")
        conn.commit()

        a1 = get_article(conn, "1")
        a2 = get_article(conn, "2")

    assert changed == 1
    assert a1 is not None and a1.is_active == 1
    assert a2 is not None and a2.is_active == 0
    assert a2.last_seen_at == "2026-02-23T00:00:00Z"


def test_get_stats_returns_aggregate_values(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    init_db(str(db_path))

    with connect(str(db_path)) as conn:
        upsert_article(conn, make_article("1", 40000, "2026-02-22T00:00:00Z"))
        upsert_article(conn, make_article("2", 50000, "2026-02-22T00:00:00Z"))
        upsert_article(conn, make_article("3", 80000, "2026-02-22T00:00:00Z"))
        conn.execute("UPDATE article SET is_active = 0 WHERE atcl_no = '3'")
        conn.commit()

        stats = get_stats(conn)

    assert stats["total_count"] == 3
    assert stats["active_count"] == 2
    assert stats["inactive_count"] == 1
    assert stats["min_price"] == 40000
    assert stats["max_price"] == 50000
    assert stats["avg_price"] == 45000.0


def test_fetch_state_upsert_and_get(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    init_db(str(db_path))

    with connect(str(db_path)) as conn:
        assert get_last_fetched_at(conn, "sejong-jiphyeon-dong") is None

        set_last_fetched_at(conn, "sejong-jiphyeon-dong", "2026-02-22T10:00:00Z")
        conn.commit()
        assert get_last_fetched_at(conn, "sejong-jiphyeon-dong") == "2026-02-22T10:00:00Z"

        set_last_fetched_at(conn, "sejong-jiphyeon-dong", "2026-02-22T12:00:00Z")
        conn.commit()
        assert get_last_fetched_at(conn, "sejong-jiphyeon-dong") == "2026-02-22T12:00:00Z"
