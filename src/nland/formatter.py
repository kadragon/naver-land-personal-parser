from __future__ import annotations

from .models import Article


def format_articles_table(articles: list[Article]) -> str:
    if not articles:
        return "No articles found."

    lines = [f"{'ATCL':<12} {'PRICE(만원)':>12} {'FLOOR':<10} {'전용(m2)':>10} {'동':<8}"]
    for article in articles:
        price = article.price_raw if article.price_raw is not None else "-"
        exclusive = f"{article.exclusive_area:.2f}" if article.exclusive_area is not None else "-"
        lines.append(
            f"{article.atcl_no:<12} {price:>12} {str(article.floor_info or '-'):10} {exclusive:>10} {str(article.building_name or '-'):8}"
        )
    return "\n".join(lines)


def format_article_detail(article: Article) -> str:
    rows = [
        ("매물번호", article.atcl_no),
        ("단지", article.complex_name or "-"),
        ("거래유형", article.trade_type or "-"),
        ("가격", article.price or "-"),
        ("층", article.floor_info or "-"),
        ("공급면적", _fmt_area(article.supply_area)),
        ("전용면적", _fmt_area(article.exclusive_area)),
        ("방향", article.direction or "-"),
        ("확인일", article.confirm_date or "-"),
        ("중개사", article.agent_name or "-"),
        ("설명", article.article_desc or "-"),
        ("활성", "Y" if article.is_active else "N"),
        ("first_seen_at", article.first_seen_at),
        ("last_seen_at", article.last_seen_at),
    ]
    return "\n".join([f"{label}: {value}" for label, value in rows])


def format_stats(stats: dict[str, int | float | None]) -> str:
    avg_value = stats.get("avg_price")
    avg_price = f"{avg_value:.2f}" if isinstance(avg_value, float) else "-"
    lines = [
        f"Total: {stats.get('total_count', 0)}",
        f"Active: {stats.get('active_count', 0)}",
        f"Inactive: {stats.get('inactive_count', 0)}",
        f"Min price(만원): {stats.get('min_price', '-')}",
        f"Max price(만원): {stats.get('max_price', '-')}",
        f"Avg price(만원): {avg_price}",
    ]
    return "\n".join(lines)


def _fmt_area(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f} m2"
