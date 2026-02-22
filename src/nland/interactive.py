from __future__ import annotations

from dataclasses import dataclass
import io
import sys
import termios
import tty
from typing import Callable, Protocol

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .db import connect, init_db, list_articles
from .formatter import format_article_detail
from .models import Article

AreaOption = tuple[str, dict[str, str | float | int]]


class FetchResultLike(Protocol):
    article_count: int
    area_count: int
    inactive_count: int
    detail_attempted: int
    detail_success: int
    detail_failed: int
    skipped: bool
    message: str


FetchAreaCallback = Callable[[str, dict[str, str | float | int]], FetchResultLike]


@dataclass(slots=True)
class ComplexOption:
    key: str
    label: str
    article_count: int


@dataclass(slots=True)
class BrowserState:
    area_index: int = 0
    complex_index: int = 0
    article_index: int = 0
    page_size: int = 12
    mode: str = "browse"  # browse | select_area | select_complex
    current_area_name: str | None = None
    current_complex_key: str | None = None
    status_message: str = ""


def _apply_back_transition(state: BrowserState, supports_area_select: bool) -> None:
    if state.mode == "browse":
        state.mode = "select_complex"
        return
    if state.mode == "select_complex":
        if supports_area_select:
            state.mode = "select_area"
        return
    if state.mode == "select_area":
        if state.current_area_name is not None:
            state.mode = "select_complex"


class RawKeyReader:
    def __init__(self, stream: io.TextIOBase) -> None:
        self._stream = stream
        self._fd = stream.fileno()
        self._original = None

    def __enter__(self) -> "RawKeyReader":
        self._original = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self._original is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original)

    def read_key(self) -> str:
        first = sys.stdin.buffer.read(1)
        if first == b"\x1b":
            second = sys.stdin.buffer.read(1)
            third = sys.stdin.buffer.read(1)
            if second == b"[" and third == b"A":
                return "up"
            if second == b"[" and third == b"B":
                return "down"
            return "esc"
        if first in (b"\r", b"\n"):
            return "enter"
        if first == b"\x03":
            return "ctrl_c"
        return first.decode("utf-8", errors="ignore")


def browse_articles(
    *,
    db_path: str,
    include_inactive: bool,
    min_price: int | None,
    max_price: int | None,
    area_options: list[AreaOption] | None = None,
    fetch_area_callback: FetchAreaCallback | None = None,
) -> int:
    if not sys.stdin.isatty():
        Console(stderr=True).print("[bold red]Error:[/bold red] --interactive requires a TTY terminal")
        return 1

    init_db(db_path)
    console = Console()
    area_options = area_options or []
    supports_area_select = bool(area_options and fetch_area_callback is not None)
    state = BrowserState(mode="select_area" if supports_area_select else "browse")

    with RawKeyReader(sys.stdin) as reader, console.screen(hide_cursor=True):
        while True:
            all_articles = _load_articles(
                db_path=db_path,
                include_inactive=include_inactive,
                min_price=min_price,
                max_price=max_price,
            )
            complex_options = _build_complex_options(all_articles)
            if complex_options and state.current_complex_key is None:
                state.current_complex_key = complex_options[0].key
            if (
                state.current_complex_key is not None
                and complex_options
                and state.current_complex_key not in {item.key for item in complex_options}
            ):
                state.current_complex_key = complex_options[0].key

            filtered_articles = _filter_articles_by_complex(all_articles, state.current_complex_key)
            if filtered_articles:
                state.article_index = max(0, min(state.article_index, len(filtered_articles) - 1))
            else:
                state.article_index = 0
            if complex_options:
                state.complex_index = max(0, min(state.complex_index, len(complex_options) - 1))
            else:
                state.complex_index = 0

            console.clear()
            if state.mode == "select_area":
                console.print(
                    _build_area_select_layout(
                        area_options=area_options,
                        state=state,
                        include_inactive=include_inactive,
                        min_price=min_price,
                        max_price=max_price,
                    )
                )
            elif state.mode == "select_complex":
                console.print(
                    _build_complex_select_layout(
                        complex_options=complex_options,
                        state=state,
                        include_inactive=include_inactive,
                        min_price=min_price,
                        max_price=max_price,
                    )
                )
            else:
                console.print(
                    _build_browse_layout(
                        articles=filtered_articles,
                        state=state,
                        include_inactive=include_inactive,
                        min_price=min_price,
                        max_price=max_price,
                        supports_area_select=supports_area_select,
                    )
                )

            key = reader.read_key()
            if key in ("q", "ctrl_c"):
                return 0
            if key == "b":
                _apply_back_transition(state, supports_area_select)
                continue

            if state.mode == "select_area":
                if key in ("down", "j"):
                    state.area_index = min(state.area_index + 1, max(len(area_options) - 1, 0))
                    continue
                if key in ("up", "k"):
                    state.area_index = max(state.area_index - 1, 0)
                    continue
                if key in ("enter", " ", "s") and area_options and fetch_area_callback is not None:
                    area_name, config = area_options[state.area_index]
                    state.status_message = f"Fetching latest data for {area_name}..."
                    console.clear()
                    console.print(
                        _build_area_select_layout(
                            area_options=area_options,
                            state=state,
                            include_inactive=include_inactive,
                            min_price=min_price,
                            max_price=max_price,
                        )
                    )
                    result = fetch_area_callback(area_name, dict(config))
                    state.current_area_name = area_name
                    state.status_message = _fetch_summary_line(result)
                    state.mode = "select_complex"
                    state.complex_index = 0
                    state.article_index = 0
                    state.current_complex_key = None
                    continue
                continue

            if state.mode == "select_complex":
                if key in ("down", "j"):
                    state.complex_index = min(state.complex_index + 1, max(len(complex_options) - 1, 0))
                    continue
                if key in ("up", "k"):
                    state.complex_index = max(state.complex_index - 1, 0)
                    continue
                if key in ("enter", " ", "s") and complex_options:
                    chosen = complex_options[state.complex_index]
                    state.current_complex_key = chosen.key
                    state.mode = "browse"
                    state.article_index = 0
                    continue
                if key == "a" and supports_area_select:
                    state.mode = "select_area"
                    continue
                continue

            if key in ("down", "j"):
                state.article_index = min(state.article_index + 1, max(len(filtered_articles) - 1, 0))
                continue
            if key in ("up", "k"):
                state.article_index = max(state.article_index - 1, 0)
                continue
            if key == "g":
                state.article_index = 0
                continue
            if key == "G":
                state.article_index = max(len(filtered_articles) - 1, 0)
                continue
            if key == "a" and supports_area_select:
                state.mode = "select_area"
                continue
            if key == "c":
                state.mode = "select_complex"
                continue
            if key == "r" and fetch_area_callback is not None and state.current_area_name is not None:
                config = _find_area_config(area_options, state.current_area_name)
                if config is not None:
                    state.status_message = f"Refreshing {state.current_area_name}..."
                    result = fetch_area_callback(state.current_area_name, dict(config))
                    state.status_message = _fetch_summary_line(result)
                continue


def _fetch_summary_line(result: FetchResultLike) -> str:
    if result.message:
        return result.message
    if result.skipped:
        return "Skipped network fetch and used cached DB data."
    return (
        f"Fetched {result.article_count} article(s), "
        f"inactive {result.inactive_count}, "
        f"detail success {result.detail_success}/{result.detail_attempted}"
    )


def _find_area_config(area_options: list[AreaOption], area_name: str) -> dict[str, str | float | int] | None:
    for name, config in area_options:
        if name == area_name:
            return config
    return None


def _load_articles(
    *,
    db_path: str,
    include_inactive: bool,
    min_price: int | None,
    max_price: int | None,
) -> list[Article]:
    with connect(db_path) as conn:
        return list_articles(
            conn,
            include_inactive=include_inactive,
            min_price=min_price,
            max_price=max_price,
        )


def _complex_key(article: Article) -> str:
    if article.complex_no:
        return f"no:{article.complex_no}"
    if article.complex_name:
        return f"name:{article.complex_name}"
    return "unknown"


def _complex_label(article: Article) -> str:
    if article.complex_name:
        return article.complex_name
    if article.complex_no:
        return f"단지번호 {article.complex_no}"
    return "미확인 단지"


def _build_complex_options(articles: list[Article]) -> list[ComplexOption]:
    grouped: dict[str, ComplexOption] = {}
    for article in articles:
        key = _complex_key(article)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = ComplexOption(key=key, label=_complex_label(article), article_count=1)
        else:
            existing.article_count += 1
    return sorted(grouped.values(), key=lambda item: item.label)


def _filter_articles_by_complex(articles: list[Article], complex_key: str | None) -> list[Article]:
    if complex_key is None:
        return articles
    return [article for article in articles if _complex_key(article) == complex_key]


def _build_area_select_layout(
    *,
    area_options: list[AreaOption],
    state: BrowserState,
    include_inactive: bool,
    min_price: int | None,
    max_price: int | None,
) -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    layout["body"].split_row(Layout(name="area"), Layout(name="help"))

    layout["header"].update(
        Panel(
            Group(
                Text("NLand Interactive Browser", style="bold cyan"),
                Text("Step 1/3: Select area, then fetch starts immediately."),
                Text("keys: ↑/↓ or j/k move • Enter/Space/s select+fetch • b back • q quit"),
            ),
            border_style="cyan",
        )
    )

    table = Table(expand=True)
    table.add_column(" ")
    table.add_column("AREA")
    for idx, (name, _) in enumerate(area_options):
        marker = "▶" if idx == state.area_index else " "
        style = "bold black on bright_white" if idx == state.area_index else ""
        table.add_row(marker, name, style=style)
    layout["area"].update(Panel(table, title="Area List", border_style="cyan"))

    status = state.status_message or "-"
    layout["help"].update(
        Panel(
            Group(
                Text(f"filters: include_inactive={include_inactive}, min_price={min_price}, max_price={max_price}"),
                Text(f"selected area: {area_options[state.area_index][0] if area_options else '-'}"),
                Text(f"status: {status}"),
                Text("left panel: area list", style="dim"),
                Text("right panel: status/help", style="dim"),
            ),
            title="Area Help",
            border_style="cyan",
        )
    )
    return layout


def _build_complex_select_layout(
    *,
    complex_options: list[ComplexOption],
    state: BrowserState,
    include_inactive: bool,
    min_price: int | None,
    max_price: int | None,
) -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    layout["body"].split_row(Layout(name="complex"), Layout(name="help"))

    layout["header"].update(
        Panel(
            Group(
                Text("NLand Interactive Browser", style="bold cyan"),
                Text("Step 2/3: Select complex, then article list opens."),
                Text("keys: ↑/↓ or j/k move • Enter/Space/s select • b back • a area • q quit"),
            ),
            border_style="cyan",
        )
    )

    table = Table(expand=True)
    table.add_column(" ")
    table.add_column("COMPLEX")
    table.add_column("COUNT", justify="right")
    for idx, item in enumerate(complex_options):
        marker = "▶" if idx == state.complex_index else " "
        style = "bold black on bright_white" if idx == state.complex_index else ""
        table.add_row(marker, item.label, str(item.article_count), style=style)
    if not complex_options:
        table.add_row("-", "No complex available", "0")
    layout["complex"].update(Panel(table, title="Complex List", border_style="cyan"))

    selected_label = complex_options[state.complex_index].label if complex_options else "-"
    status = state.status_message or "-"
    layout["help"].update(
        Panel(
            Group(
                Text(f"area: {state.current_area_name or '-'}"),
                Text(f"selected complex: {selected_label}"),
                Text(f"filters: include_inactive={include_inactive}, min_price={min_price}, max_price={max_price}"),
                Text(f"status: {status}"),
                Text("left panel: complex list", style="dim"),
                Text("right panel: status/help", style="dim"),
            ),
            title="Complex Help",
            border_style="cyan",
        )
    )
    return layout


def _build_browse_layout(
    *,
    articles: list[Article],
    state: BrowserState,
    include_inactive: bool,
    min_price: int | None,
    max_price: int | None,
    supports_area_select: bool,
) -> Layout:
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    layout["body"].split_row(Layout(name="list"), Layout(name="detail"))

    area_text = state.current_area_name or "-"
    help_text = "keys: ↑/↓ or j/k move • g/G top/bottom • c complex • b back • r refresh • q quit"
    if supports_area_select:
        help_text += " • a area"
    status = state.status_message or "-"
    layout["header"].update(
        Panel(
            Group(
                Text("NLand Interactive Browser", style="bold cyan"),
                Text(f"Step 3/3: Browse articles • area: {area_text} • filters: include_inactive={include_inactive}, min_price={min_price}, max_price={max_price}"),
                Text(help_text),
                Text(f"status: {status}"),
                Text("left panel: article list / right panel: selected article detail", style="dim"),
            ),
            border_style="cyan",
        )
    )

    if not articles:
        layout["list"].update(Panel("No articles in this complex.\nPress c to choose another complex.", title="Article List", border_style="cyan"))
        layout["detail"].update(Panel("No selected article.", title="Article Detail", border_style="cyan"))
        return layout

    layout["list"].update(Panel(_build_list_table(articles, state), title="Article List", border_style="cyan"))
    selected = articles[state.article_index]
    layout["detail"].update(
        Panel(format_article_detail(selected), title="Article Detail", border_style="cyan")
    )
    return layout


def _build_list_table(articles: list[Article], state: BrowserState) -> Table:
    table = Table(expand=True)
    table.add_column(" ")
    table.add_column("ATCL", style="cyan")
    table.add_column("PRICE", justify="right", style="green")
    table.add_column("평당단가", justify="right", style="yellow")
    table.add_column("FLOOR")
    table.add_column("평수(전용/공급)", justify="right")

    total = len(articles)
    if total <= state.page_size:
        start = 0
        end = total
    else:
        half = state.page_size // 2
        start = max(0, min(state.article_index - half, total - state.page_size))
        end = start + state.page_size

    for idx in range(start, end):
        article = articles[idx]
        marker = "▶" if idx == state.article_index else " "
        style = "bold black on bright_white" if idx == state.article_index else ""
        table.add_row(
            marker,
            article.atcl_no,
            str(article.price_raw) if article.price_raw is not None else "-",
            _to_price_per_pyeong_text(article.price_raw, article.exclusive_area),
            article.floor_info or "-",
            _to_pyeong_pair_text(article.exclusive_area, article.supply_area),
            style=style,
        )
    return table


def _to_pyeong_text(area: float | None) -> str:
    if area is None:
        return "-"
    return f"{area / 3.305785:.1f}"


def _to_pyeong_pair_text(exclusive_area: float | None, supply_area: float | None) -> str:
    return f"{_to_pyeong_text(exclusive_area)}/{_to_pyeong_text(supply_area)}"


def _to_price_per_pyeong_text(price_raw: int | None, exclusive_area: float | None) -> str:
    if price_raw is None or exclusive_area is None:
        return "-"
    pyeong = exclusive_area / 3.305785
    if pyeong <= 0:
        return "-"
    unit_price = round(price_raw / pyeong)
    return f"{unit_price:,}"
