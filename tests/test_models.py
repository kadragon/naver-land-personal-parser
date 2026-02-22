from __future__ import annotations

import json
import pytest

from nland.models import parse_article, parse_price


def test_parse_price_with_eok_and_rest() -> None:
    assert parse_price("7억 5,000") == 75000


def test_parse_price_with_eok_only() -> None:
    assert parse_price("7억") == 70000


def test_parse_price_without_eok() -> None:
    assert parse_price("5,000") == 5000


def test_parse_price_raises_value_error_for_invalid_input() -> None:
    with pytest.raises(ValueError):
        parse_price("가격문의")


def test_parse_article_maps_fields_and_timestamps() -> None:
    now = "2026-02-22T12:00:00Z"
    payload = {
        "atclNo": "2429861377",
        "hscpNo": "12345",
        "hscpNm": "집현파크",
        "tradTpNm": "매매",
        "bildNm": "101동",
        "flrInfo": "5/15",
        "prcInfo": "4억 5,000",
        "spc1": "84.99",
        "spc2": "59.99",
        "direction": "남향",
        "cfmYmd": "2026-02-20",
        "rltrNm": "행복공인",
        "atclFetrDesc": "채광 우수",
    }

    article = parse_article(payload, now)

    assert article.atcl_no == "2429861377"
    assert article.price_raw == 45000
    assert article.supply_area == 84.99
    assert article.exclusive_area == 59.99
    assert article.first_seen_at == now
    assert article.last_seen_at == now
    assert article.is_active == 1
    assert json.loads(article.raw_json)["atclNo"] == "2429861377"


def test_parse_article_uses_hanprc_when_prcinfo_missing() -> None:
    now = "2026-02-22T12:00:00Z"
    payload = {
        "atclNo": "2609812997",
        "hanPrc": "9억 8,000",
        "prc": 98000,
    }

    article = parse_article(payload, now)

    assert article.price == "9억 8,000"
    assert article.price_raw == 98000


def test_parse_article_uses_atclnm_when_hscpnm_missing() -> None:
    now = "2026-02-22T12:00:00Z"
    payload = {
        "atclNo": "2609812997",
        "atclNm": "새나루1단지자이e편한세상",
        "prcInfo": "9억 8,000",
    }

    article = parse_article(payload, now)

    assert article.complex_name == "새나루1단지자이e편한세상"


def test_parse_article_maps_extended_metadata_fields() -> None:
    now = "2026-02-22T12:00:00Z"
    payload = {
        "atclNo": "2609812997",
        "prcInfo": "9억 8,000",
        "tagList": ["10년이내", "대단지", "방네개이상"],
        "cpNm": "매경부동산",
        "lat": 36.48654,
        "lng": 127.31807,
        "repImgUrl": "/some/image.jpg",
    }

    article = parse_article(payload, now)

    assert article.tag_list == "[\"10년이내\", \"대단지\", \"방네개이상\"]"
    assert article.cp_name == "매경부동산"
    assert article.latitude == 36.48654
    assert article.longitude == 127.31807
    assert article.rep_img_url == "/some/image.jpg"
