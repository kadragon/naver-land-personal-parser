## Models - Price Parsing

> Parse Naver style price text into integer 만원 values for sorting/filtering.

- [x] `parse_price("7억 5,000")` returns `75000`

## Models - Article Parsing

> Convert raw API payloads into normalized `Article` objects.

- [x] `parse_article()` maps core fields and UTC timestamps

## Database - Initialization

> Ensure a local SQLite schema is always ready before reads/writes.

- [x] `init_db()` creates `article` table with required columns

## Database - Upsert and Seen Tracking

> Preserve listing history while updating latest snapshot values.

- [x] `upsert_article()` inserts and updates while preserving `first_seen_at`

## Database - Listing and Detail Query

> Provide filtered article queries for list/detail commands.

- [x] `list_articles()` supports active/all and min/max price filters

## Database - Inactive Handling

> Keep delisted history without physical delete.

- [x] `mark_inactive()` deactivates currently missing listings only

## Database - Stats

> Expose counts and price aggregates for quick CLI insight.

- [x] `get_stats()` returns total/active/inactive and min/max/avg for active items

## Formatter - CLI Output

> Render readable table/detail/stats text in terminal.

- [x] formatter functions produce stable human-readable output

## Client - Naver API Calls

> Fetch listing pages and detail payloads with required headers and delay.

- [x] `NaverLandClient` handles pagination, headers, API errors, and detail payloads

## CLI - Routing

> Route subcommands and options to underlying module handlers.

- [x] argparse wiring supports `fetch`, `list`, `detail`, `stats`, and `--db`

## CLI - End-to-End Flow

> Run end-user workflows that combine client, DB, parser, and formatter.

- [x] `fetch/list/detail/stats` integrate correctly including detail remote fallback
