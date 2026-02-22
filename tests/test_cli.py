from __future__ import annotations

from pathlib import Path

from nland import db
from nland.cli import _should_skip_area_fetch, main
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
        tag_list='["대단지"]',
        cp_name="매경부동산",
        latitude=36.49,
        longitude=127.32,
        rep_img_url="/image.jpg",
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
        def fetch_article_list(self, **kwargs):
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
    assert "Fetched 1 unique articles from 1 area(s)" in out

    with db.connect(str(db_path)) as conn:
        saved = db.get_article(conn, "1001")
    assert saved is not None


def test_fetch_with_detail_merges_extended_fields(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "data.db"

    class FakeClient:
        def fetch_article_list(self, **kwargs):
            return [{"atclNo": "1001", "atclNm": "집현테스트", "prcInfo": "4억"}]

        def fetch_article_detail(self, article_id: str):
            return {
                "atclNo": article_id,
                "tagList": ["대단지", "방세개"],
                "cpNm": "매경부동산",
                "lat": 36.48654,
                "lng": 127.31807,
                "repImgUrl": "/image.jpg",
            }

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)
    monkeypatch.setattr("nland.cli.utc_now", lambda: "2026-02-22T00:00:00Z")

    code = main(["--db", str(db_path), "fetch", "--with-detail"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Detail attempted 1, success 1, failed 0" in out

    with db.connect(str(db_path)) as conn:
        saved = db.get_article(conn, "1001")

    assert saved is not None
    assert saved.cp_name == "매경부동산"
    assert saved.tag_list == "[\"대단지\", \"방세개\"]"


def test_list_applies_price_filters(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "data.db"
    db.init_db(str(db_path))

    with db.connect(str(db_path)) as conn:
        db.upsert_article(conn, make_article("10001", 40000, "2026-02-22T00:00:00Z"))
        db.upsert_article(conn, make_article("20002", 70000, "2026-02-22T00:00:00Z"))
        conn.commit()

    code = main(["--db", str(db_path), "list", "--min-price", "50000", "--max-price", "80000"])

    assert code == 0
    out = capsys.readouterr().out
    assert "20002" in out
    assert "10001" not in out


def test_list_interactive_dispatches_to_browser(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "data.db"
    called: dict[str, object] = {}

    def fake_browse_articles(
        *,
        db_path: str,
        include_inactive: bool,
        min_price: int | None,
        max_price: int | None,
        area_options,
        fetch_area_callback,
    ) -> int:
        called.update(
            {
                "db_path": db_path,
                "include_inactive": include_inactive,
                "min_price": min_price,
                "max_price": max_price,
                "area_options": area_options,
                "fetch_area_callback": fetch_area_callback,
            }
        )
        return 0

    monkeypatch.setattr("nland.cli.browse_articles", fake_browse_articles)

    code = main(
        [
            "--db",
            str(db_path),
            "list",
            "--interactive",
            "--all",
            "--min-price",
            "30000",
            "--max-price",
            "90000",
        ]
    )

    assert code == 0
    assert called["db_path"] == str(db_path)
    assert called["include_inactive"] is True
    assert called["min_price"] == 30000
    assert called["max_price"] == 90000
    assert called["area_options"] == [
        (
            "sejong-jiphyeon-dong",
            {
                "cortar_no": "3611011800",
                "lat": 36.499226,
                "lon": 127.329209,
                "z": 14,
                "span": 0.02,
            },
        )
    ]
    assert callable(called["fetch_area_callback"])


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


def test_fetch_supports_repeatable_area_and_custom_area(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "data.db"
    calls: list[dict] = []

    class FakeClient:
        def fetch_article_list(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("cortar_no") == "3611011800":
                return [{"atclNo": "1001", "prcInfo": "4억"}]
            return [{"atclNo": "2001", "prcInfo": "5억"}]

    monkeypatch.setattr("nland.cli.NaverLandClient", FakeClient)
    monkeypatch.setattr("nland.cli.utc_now", lambda: "2026-02-22T00:00:00Z")

    code = main(
        [
            "--db",
            str(db_path),
            "fetch",
            "--area",
            "sejong-jiphyeon-dong",
            "--cortar-no",
            "3611019999",
            "--lat",
            "36.50",
            "--lon",
            "127.30",
        ]
    )

    assert code == 0
    assert len(calls) == 2
    out = capsys.readouterr().out
    assert "Fetched 2 unique articles from 2 area(s)" in out


def test_should_skip_area_fetch_when_within_ttl() -> None:
    assert _should_skip_area_fetch(
        last_fetched_at="2026-02-22T08:30:00Z",
        now_utc="2026-02-22T12:00:00Z",
        ttl_hours=6,
    )


def test_should_not_skip_area_fetch_when_ttl_expired() -> None:
    assert not _should_skip_area_fetch(
        last_fetched_at="2026-02-22T04:00:00Z",
        now_utc="2026-02-22T12:00:00Z",
        ttl_hours=6,
    )
