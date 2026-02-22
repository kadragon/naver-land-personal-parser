from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys

from .client import NaverLandClient
from .db import connect, get_article, get_stats, init_db, list_articles, mark_inactive, upsert_article
from .formatter import format_article_detail, format_articles_table, format_stats
from .models import parse_article


DEFAULT_DB_PATH = "~/.nland/data.db"


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_fetch(args: argparse.Namespace) -> int:
    init_db(args.db)
    client = NaverLandClient()
    now = utc_now()

    raw_articles = client.fetch_article_list()
    articles = [parse_article(payload, now) for payload in raw_articles]
    active_ids = {article.atcl_no for article in articles}

    with connect(args.db) as conn:
        conn.execute("BEGIN")
        for article in articles:
            upsert_article(conn, article)
        inactive_count = mark_inactive(conn, active_ids, now)
        conn.commit()

    print(f"Fetched {len(articles)} articles ({inactive_count} marked inactive).")
    return 0


def handle_list(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        articles = list_articles(
            conn,
            include_inactive=args.all,
            min_price=args.min_price,
            max_price=args.max_price,
        )
    print(format_articles_table(articles))
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
            print(f"Error: failed to fetch detail for {args.atcl_no}: {exc}", file=sys.stderr)
            return 1

        if "atclNo" not in payload:
            payload = {**payload, "atclNo": args.atcl_no}

        try:
            article = parse_article(payload, utc_now())
        except ValueError as exc:
            print(f"Error: invalid article detail payload: {exc}", file=sys.stderr)
            return 1

        with connect(args.db) as conn:
            upsert_article(conn, article)
            conn.commit()

    print(format_article_detail(article))
    return 0


def handle_stats(args: argparse.Namespace) -> int:
    init_db(args.db)
    with connect(args.db) as conn:
        stats = get_stats(conn)
    print(format_stats(stats))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="nland")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.set_defaults(func=handle_fetch)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--all", action="store_true", help="include inactive articles")
    list_parser.add_argument("--min-price", type=int)
    list_parser.add_argument("--max-price", type=int)
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
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
