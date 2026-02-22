from __future__ import annotations

from pathlib import Path

from nland import db
from nland.cli import main
from nland.models import Article


def make_article(atcl_no: str, price_raw: int, now: str, *, is_active: int = 1) -> Article:
    return Article(
        atcl_no=atcl_no,
        complex_no="100",
        complex_name="집현파크",
        trade_type="매매",
        building_name="101동",
        floor_info="5/15",
        price="4억 5,000",
        price_raw=price_raw,
        supply_area=84.99,
        exclusive_area=59.99,
        direction="남향",
        confirm_date="2026-02-20",
        agent_name="행복공인",
        article_desc="채광 우수",
        raw_json="{}",
        first_seen_at=now,
        last_seen_at=now,
        is_active=is_active,
    )


def test_fetch_collects_articles_and_prints_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "data.db"

    class FakeClient:
        def fetch_article_list(self):
            return [
                {
                    "atclNo": "1001",
                    "hscpNo": "100",
                    "hscpNm": "집현파크",
                    "tradTpNm": "매매",
                    "bildNm": "101동",
                    "flrInfo": "5/15",
                    "prcInfo": "4억 5,000",
                    "spc1": "84.99",
                    "spc2": "59.99",
                }
            ]

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)
    monkeypatch.setattr("nland.cli.utc_now", lambda: "2026-02-22T00:00:00Z")

    code = main(["--db", str(db_path), "fetch"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Fetched 1 articles" in out

    with db.connect(str(db_path)) as conn:
        saved = db.get_article(conn, "1001")
    assert saved is not None


def test_list_applies_price_filters(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "data.db"
    db.init_db(str(db_path))

    with db.connect(str(db_path)) as conn:
        db.upsert_article(conn, make_article("1", 40000, "2026-02-22T00:00:00Z"))
        db.upsert_article(conn, make_article("2", 70000, "2026-02-22T00:00:00Z"))
        conn.commit()

    code = main(["--db", str(db_path), "list", "--min-price", "50000", "--max-price", "80000"])

    assert code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line and not line.startswith("ATCL")]
    assert any(line.strip().startswith("2") for line in lines)
    assert all(not line.strip().startswith("1") for line in lines)


def test_detail_uses_local_db_when_present(tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "data.db"
    db.init_db(str(db_path))

    with db.connect(str(db_path)) as conn:
        db.upsert_article(conn, make_article("1", 40000, "2026-02-22T00:00:00Z"))
        conn.commit()

    class FakeClient:
        called = False

        def fetch_article_detail(self, article_id: str):
            self.called = True
            raise AssertionError("remote should not be called")

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)

    code = main(["--db", str(db_path), "detail", "1"])

    assert code == 0
    out = capsys.readouterr().out
    assert "매물번호: 1" in out


def test_detail_fetches_remote_and_stores_when_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "data.db"

    class FakeClient:
        def fetch_article_detail(self, article_id: str):
            return {
                "atclNo": article_id,
                "hscpNm": "집현파크",
                "tradTpNm": "매매",
                "prcInfo": "5억",
                "flrInfo": "10/20",
            }

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)
    monkeypatch.setattr("nland.cli.utc_now", lambda: "2026-02-22T00:00:00Z")

    code = main(["--db", str(db_path), "detail", "555"])

    assert code == 0
    out = capsys.readouterr().out
    assert "매물번호: 555" in out

    with db.connect(str(db_path)) as conn:
        saved = db.get_article(conn, "555")
    assert saved is not None


def test_stats_prints_summary(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "data.db"
    db.init_db(str(db_path))

    with db.connect(str(db_path)) as conn:
        db.upsert_article(conn, make_article("1", 40000, "2026-02-22T00:00:00Z"))
        db.upsert_article(conn, make_article("2", 70000, "2026-02-22T00:00:00Z"))
        conn.execute("UPDATE article SET is_active = 0 WHERE atcl_no = '2'")
        conn.commit()

    code = main(["--db", str(db_path), "stats"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Total: 2" in out
    assert "Active: 1" in out
    assert "Inactive: 1" in out


def test_invalid_args_and_missing_remote_returns_code_1(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "data.db"

    bad_code = main(["--db", str(db_path), "detail"])
    assert bad_code == 1

    class FakeClient:
        def fetch_article_detail(self, article_id: str):
            raise RuntimeError("not found")

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)

    missing_code = main(["--db", str(db_path), "detail", "9999"])

    assert missing_code == 1
    err = capsys.readouterr().err
    assert "Error:" in err
