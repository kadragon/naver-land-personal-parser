from __future__ import annotations

from typing import Any

from nland.models import Article


def make_article(
    atcl_no: str = "1",
    price_raw: int = 45000,
    now: str = "2026-02-22T00:00:00Z",
    *,
    is_active: int = 1,
    **overrides: Any,
) -> Article:
    payload: dict[str, Any] = {
        "atcl_no": atcl_no,
        "complex_no": "100",
        "complex_name": "집현파크",
        "trade_type": "매매",
        "building_name": "101동",
        "floor_info": "5/15",
        "price": "4억 5,000",
        "price_raw": price_raw,
        "supply_area": 84.99,
        "exclusive_area": 59.99,
        "direction": "남향",
        "confirm_date": "2026-02-20",
        "agent_name": "행복공인",
        "article_desc": "채광 우수",
        "tag_list": '["대단지"]',
        "cp_name": "매경부동산",
        "latitude": 36.49,
        "longitude": 127.32,
        "rep_img_url": "/image.jpg",
        "raw_json": "{}",
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": is_active,
    }
    payload.update(overrides)
    return Article(**payload)
