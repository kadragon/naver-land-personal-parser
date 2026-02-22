from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rich.console import Console

from .client import NaverLandClient
from .db import (
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
from .formatter import render_article_detail, render_articles, render_fetch_summary, render_stats
from .interactive import browse_articles
from .models import parse_article


DEFAULT_DB_PATH = "~/.nland/data.db"
DEFAULT_FETCH_AREA = "sejong-jiphyeon-dong"
INTERACTIVE_FETCH_CACHE_TTL_HOURS = 6
FETCH_AREA_PRESETS: dict[str, dict[str, str | float | int]] = {
    DEFAULT_FETCH_AREA: {
        "cortar_no": "3611011800",
        "lat": 36.499226,
        "lon": 127.329209,
        "z": 14,
        "span": 0.02,
    },
}
CONSOLE = Console()
ERROR_CONSOLE = Console(stderr=True)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class FetchResult:
    article_count: int
    area_count: int
    inactive_count: int
    detail_attempted: int
    detail_success: int
    detail_failed: int
    skipped: bool = False
    message: str = ""


def _build_custom_fetch_area(args: argparse.Namespace) -> tuple[str, dict[str, str | float | int]] | None:
    custom_fields = [args.cortar_no, args.lat, args.lon]
    has_custom_field = any(value is not None for value in custom_fields)
    if not has_custom_field:
        return None
    if None in custom_fields:
        raise ValueError("custom area requires --cortar-no, --lat, and --lon together")

    return (
        args.custom_area_name or "custom",
        {
            "cortar_no": args.cortar_no,
            "lat": args.lat,
            "lon": args.lon,
            "z": args.z,
            "span": args.span,
        },
    )


def _resolve_fetch_areas(
    args: argparse.Namespace,
) -> list[tuple[str, dict[str, str | float | int]]]:
    areas = args.area or [DEFAULT_FETCH_AREA]
    resolved: list[tuple[str, dict[str, str | float | int]]] = []

    for area in areas:
        config = FETCH_AREA_PRESETS.get(area)
        if config is None:
            known = ", ".join(sorted(FETCH_AREA_PRESETS.keys()))
            raise ValueError(f"unknown --area '{area}'. available: {known}")
        resolved.append((area, dict(config)))

    custom_area = _build_custom_fetch_area(args)
    if custom_area is not None:
        resolved.append(custom_area)

    return resolved


def _parse_utc(utc_text: str) -> datetime:
    return datetime.strptime(utc_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _should_skip_area_fetch(
    *,
    last_fetched_at: str | None,
    now_utc: str,
    ttl_hours: int,
) -> bool:
    if last_fetched_at is None:
        return False
    try:
        now_dt = _parse_utc(now_utc)
        last_dt = _parse_utc(last_fetched_at)
    except ValueError:
        return False
    return now_dt - last_dt < timedelta(hours=ttl_hours)


def _fetch_areas_to_db(
    *,
    db_path: str,
    areas: list[tuple[str, dict[str, str | float | int]]],
    with_detail: bool,
) -> FetchResult:
    init_db(db_path)
    client = NaverLandClient()
    now = utc_now()

    merged_payloads: dict[str, dict] = {}
    for _, config in areas:
        raw_articles = client.fetch_article_list(**config)
        for payload in raw_articles:
            atcl_no = str(payload.get("atclNo") or "")
            if atcl_no:
                merged_payloads[atcl_no] = payload

    detail_attempted = 0
    detail_success = 0
    detail_failed = 0
    if with_detail:
        for atcl_no, payload in list(merged_payloads.items()):
            detail_attempted += 1
            try:
                detail_payload = client.fetch_article_detail(atcl_no)
            except Exception:  # noqa: BLE001
                detail_failed += 1
                continue
            detail_success += 1
            merged_payloads[atcl_no] = {**payload, **detail_payload, "atclNo": atcl_no}

    articles = [parse_article(payload, now) for payload in merged_payloads.values()]
    active_ids = {article.atcl_no for article in articles}

    with connect(db_path) as conn:
        conn.execute("BEGIN")
        for article in articles:
            upsert_article(conn, article)
        inactive_count = mark_inactive(conn, active_ids, now)
        for area_name, _ in areas:
            set_last_fetched_at(conn, area_name, now)
        conn.commit()

    return FetchResult(
        article_count=len(articles),
        area_count=len(areas),
        inactive_count=inactive_count,
        detail_attempted=detail_attempted,
        detail_success=detail_success,
        detail_failed=detail_failed,
    )


def handle_fetch(args: argparse.Namespace) -> int:
    areas = _resolve_fetch_areas(args)
    result = _fetch_areas_to_db(
        db_path=args.db,
        areas=areas,
        with_detail=args.with_detail,
    )

    CONSOLE.print(
        render_fetch_summary(
            article_count=result.article_count,
            area_count=result.area_count,
            inactive_count=result.inactive_count,
            detail_attempted=result.detail_attempted if args.with_detail else None,
            detail_success=result.detail_success if args.with_detail else None,
            detail_failed=result.detail_failed if args.with_detail else None,
        )
    )
    return 0


def handle_list(args: argparse.Namespace) -> int:
    if args.interactive:
        area_options = [(name, dict(config)) for name, config in FETCH_AREA_PRESETS.items()]

        def fetch_selected_area(area_name: str, config: dict[str, str | float | int]) -> FetchResult:
            now = utc_now()
            with connect(args.db) as conn:
                last_fetched_at = get_last_fetched_at(conn, area_name)

            if _should_skip_area_fetch(
                last_fetched_at=last_fetched_at,
                now_utc=now,
                ttl_hours=INTERACTIVE_FETCH_CACHE_TTL_HOURS,
            ):
                with connect(args.db) as conn:
                    cached_articles = list_articles(
                        conn,
                        include_inactive=args.all,
                        min_price=args.min_price,
                        max_price=args.max_price,
                    )
                return FetchResult(
                    article_count=len(cached_articles),
                    area_count=1,
                    inactive_count=0,
                    detail_attempted=0,
                    detail_success=0,
                    detail_failed=0,
                    skipped=True,
                    message=(
                        f"Skipped network fetch for {area_name}. "
                        f"Using cached DB data (last fetched: {last_fetched_at}, "
                        f"TTL {INTERACTIVE_FETCH_CACHE_TTL_HOURS}h)."
                    ),
                )

            return _fetch_areas_to_db(
                db_path=args.db,
                areas=[(area_name, config)],
                with_detail=False,
            )

        return browse_articles(
            db_path=args.db,
            include_inactive=args.all,
            min_price=args.min_price,
            max_price=args.max_price,
            area_options=area_options,
            fetch_area_callback=fetch_selected_area,
        )

    init_db(args.db)
    with connect(args.db) as conn:
        articles = list_articles(
            conn,
            include_inactive=args.all,
            min_price=args.min_price,
            max_price=args.max_price,
        )
    CONSOLE.print(render_articles(articles))
    return 0


def handle_detail(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        article = get_article(conn, args.atcl_no)

    if article is None:
        client = NaverLandClient()
        try:
            payload = client.fetch_article_detail(args.atcl_no)
        except Exception as exc:  # noqa: BLE001
            ERROR_CONSOLE.print(f"[bold red]Error:[/bold red] failed to fetch detail for {args.atcl_no}: {exc}")
            return 1

        if "atclNo" not in payload:
            payload = {**payload, "atclNo": args.atcl_no}

        try:
            article = parse_article(payload, utc_now())
        except ValueError as exc:
            ERROR_CONSOLE.print(f"[bold red]Error:[/bold red] invalid article detail payload: {exc}")
            return 1

        with connect(args.db) as conn:
            upsert_article(conn, article)
            conn.commit()

    CONSOLE.print(render_article_detail(article))
    return 0


def handle_stats(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        stats = get_stats(conn)
    CONSOLE.print(render_stats(stats))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="nland")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument(
        "--area",
        action="append",
        help=(
            "preset area key (repeatable). "
            f"default: {DEFAULT_FETCH_AREA}. "
            f"available: {', '.join(sorted(FETCH_AREA_PRESETS.keys()))}"
        ),
    )
    fetch_parser.add_argument("--cortar-no", help="custom area cortarNo")
    fetch_parser.add_argument("--lat", type=float, help="custom area center latitude")
    fetch_parser.add_argument("--lon", type=float, help="custom area center longitude")
    fetch_parser.add_argument("--z", type=int, default=14, help="custom area zoom")
    fetch_parser.add_argument("--span", type=float, default=0.02, help="custom area viewport half-span")
    fetch_parser.add_argument(
        "--custom-area-name",
        default="custom",
        help="label for custom area in logs",
    )
    fetch_parser.add_argument(
        "--with-detail",
        action="store_true",
        help="fetch and merge per-article detail API fields",
    )
    fetch_parser.set_defaults(func=handle_fetch)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--all", action="store_true", help="include inactive articles")
    list_parser.add_argument("--min-price", type=int)
    list_parser.add_argument("--max-price", type=int)
    list_parser.add_argument(
        "--interactive",
        action="store_true",
        help="open keyboard-driven interactive browser",
    )
    list_parser.set_defaults(func=handle_list)

    detail_parser = subparsers.add_parser("detail")
    detail_parser.add_argument("atcl_no")
    detail_parser.set_defaults(func=handle_detail)

    stats_parser = subparsers.add_parser("stats")
    stats_parser.set_defaults(func=handle_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except ValueError as exc:
        ERROR_CONSOLE.print(f"[bold red]Error:[/bold red] {exc}")
        return 1

    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        ERROR_CONSOLE.print(f"[bold red]Error:[/bold red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
