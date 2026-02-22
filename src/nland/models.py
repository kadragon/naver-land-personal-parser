from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(slots=True)
class Article:
    atcl_no: str
    complex_no: str | None
    complex_name: str | None
    trade_type: str | None
    building_name: str | None
    floor_info: str | None
    price: str | None
    price_raw: int | None
    supply_area: float | None
    exclusive_area: float | None
    direction: str | None
    confirm_date: str | None
    agent_name: str | None
    article_desc: str | None
    raw_json: str
    first_seen_at: str
    last_seen_at: str
    is_active: int = 1


def _pick(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _to_float(value: str | int | float | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_price(text: str) -> int:
    if text is None:
        raise ValueError("price text is required")

    normalized = text.strip().replace(" ", "")
    if not normalized:
        raise ValueError("price text is empty")

    if "억" in normalized:
        parts = normalized.split("억")
        if len(parts) != 2:
            raise ValueError(f"invalid price format: {text}")
        upper, lower = parts
        if not upper or not upper.isdigit():
            raise ValueError(f"invalid 억 unit: {text}")
        total = int(upper) * 10000
        if lower:
            lower_value = lower.replace(",", "")
            if not lower_value.isdigit():
                raise ValueError(f"invalid lower unit: {text}")
            total += int(lower_value)
        return total

    raw = normalized.replace(",", "")
    if not raw.isdigit():
        raise ValueError(f"invalid price format: {text}")
    return int(raw)


def parse_article(payload: dict, now_utc: str) -> Article:
    atcl_no = _pick(payload, "atclNo", "articleId", "atcl_no")
    if not atcl_no:
        raise ValueError("article id (atclNo) is required")

    price = _pick(payload, "prcInfo", "price")
    price_raw = parse_price(price) if price else None

    return Article(
        atcl_no=atcl_no,
        complex_no=_pick(payload, "hscpNo", "complexNo"),
        complex_name=_pick(payload, "hscpNm", "complexName"),
        trade_type=_pick(payload, "tradTpNm", "tradeType"),
        building_name=_pick(payload, "bildNm", "buildingName"),
        floor_info=_pick(payload, "flrInfo", "floorInfo"),
        price=price,
        price_raw=price_raw,
        supply_area=_to_float(payload.get("spc1") or payload.get("supplyArea")),
        exclusive_area=_to_float(payload.get("spc2") or payload.get("exclusiveArea")),
        direction=_pick(payload, "direction"),
        confirm_date=_pick(payload, "cfmYmd", "confirmDate"),
        agent_name=_pick(payload, "rltrNm", "agentName"),
        article_desc=_pick(payload, "atclFetrDesc", "articleDesc"),
        raw_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        first_seen_at=now_utc,
        last_seen_at=now_utc,
        is_active=1,
    )
