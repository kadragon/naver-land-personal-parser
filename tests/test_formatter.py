from __future__ import annotations

from nland.formatter import format_article_detail, format_articles_table, format_stats
from nland.models import Article


def make_article() -> Article:
    return Article(
        atcl_no="1",
        complex_no="100",
        complex_name="집현파크",
        trade_type="매매",
        building_name="101동",
        floor_info="5/15",
        price="4억 5,000",
        price_raw=45000,
        supply_area=84.99,
        exclusive_area=59.99,
        direction="남향",
        confirm_date="2026-02-20",
        agent_name="행복공인",
        article_desc="채광 우수",
        tag_list='["대단지","방세개"]',
        cp_name="매경부동산",
        latitude=36.48654,
        longitude=127.31807,
        rep_img_url="/image.jpg",
        raw_json="{}",
        first_seen_at="2026-02-22T00:00:00Z",
        last_seen_at="2026-02-22T00:00:00Z",
        is_active=1,
    )


def test_format_articles_table_renders_header_and_rows() -> None:
    output = format_articles_table([make_article()])

    assert "ATCL" in output
    assert "1" in output
    assert "45000" in output


def test_format_articles_table_handles_empty_list() -> None:
    assert format_articles_table([]) == "No articles found."


def test_format_article_detail_contains_core_fields() -> None:
    output = format_article_detail(make_article())

    assert "매물번호: 1" in output
    assert "단지: 집현파크" in output
    assert "가격: 4억 5,000" in output
    assert "태그: [\"대단지\",\"방세개\"]" in output
    assert "플랫폼: 매경부동산" in output
    assert "좌표: 36.48654, 127.31807" in output
    assert "대표이미지: /image.jpg" in output


def test_format_stats_renders_consistent_layout() -> None:
    output = format_stats(
        {
            "total_count": 3,
            "active_count": 2,
            "inactive_count": 1,
            "min_price": 40000,
            "max_price": 50000,
            "avg_price": 45000.0,
        }
    )

    assert "Total: 3" in output
    assert "Active: 2" in output
    assert "Inactive: 1" in output
    assert "Avg price(만원): 45000.00" in output
