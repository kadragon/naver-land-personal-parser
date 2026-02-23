from __future__ import annotations

from dataclasses import dataclass

from nland.interactive import (
    BrowserState,
    _apply_back_transition,
    _build_complex_options,
    _filter_articles_by_complex,
    _to_price_per_pyeong_text,
    _to_pyeong_pair_text,
    _to_pyeong_text,
    browse_articles,
)
from nland.models import Article


def _make_article(atcl_no: str, complex_no: str | None, complex_name: str | None) -> Article:
    return Article(
        atcl_no=atcl_no,
        complex_no=complex_no,
        complex_name=complex_name,
        trade_type="매매",
        building_name="101동",
        floor_info="5/15",
        price="4억",
        price_raw=40000,
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
        first_seen_at="2026-02-22T00:00:00Z",
        last_seen_at="2026-02-22T00:00:00Z",
        is_active=1,
    )


def test_browse_articles_requires_tty(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    code = browse_articles(
        db_path="/tmp/nland-interactive-test.db",
        include_inactive=False,
        min_price=None,
        max_price=None,
    )

    assert code == 1


def test_build_complex_options_groups_and_counts() -> None:
    articles = [
        _make_article("1", "100", "새나루1단지"),
        _make_article("2", "100", "새나루1단지"),
        _make_article("3", "200", "새나루2단지"),
    ]

    options = _build_complex_options(articles)

    assert len(options) == 2
    labels = [item.label for item in options]
    counts = [item.article_count for item in options]
    assert labels == ["새나루1단지", "새나루2단지"]
    assert counts == [2, 1]


def test_filter_articles_by_complex_key() -> None:
    articles = [
        _make_article("1", "100", "새나루1단지"),
        _make_article("2", "100", "새나루1단지"),
        _make_article("3", "200", "새나루2단지"),
    ]

    filtered = _filter_articles_by_complex(articles, "no:100")

    assert [item.atcl_no for item in filtered] == ["1", "2"]


def test_to_pyeong_text_formats_one_decimal() -> None:
    assert _to_pyeong_text(59.99) == "18.1"


def test_to_pyeong_pair_text_formats_exclusive_and_supply() -> None:
    assert _to_pyeong_pair_text(59.99, 84.99) == "18.1/25.7"
    assert _to_pyeong_pair_text(None, 84.99) == "-/25.7"
    assert _to_pyeong_pair_text(59.99, None) == "18.1/-"


def test_to_price_per_pyeong_text_formats_unit_price() -> None:
    assert _to_price_per_pyeong_text(40000, 59.99) == "2,204"
    assert _to_price_per_pyeong_text(None, 59.99) == "-"
    assert _to_price_per_pyeong_text(40000, None) == "-"


def test_apply_back_transition_moves_to_previous_step() -> None:
    state = BrowserState(mode="browse")
    _apply_back_transition(state, supports_area_select=True)
    assert state.mode == "select_complex"

    _apply_back_transition(state, supports_area_select=True)
    assert state.mode == "select_area"


def test_apply_back_transition_from_area_returns_to_complex_when_selected() -> None:
    state = BrowserState(mode="select_area", current_area_name="sejong-jiphyeon-dong")
    _apply_back_transition(state, supports_area_select=True)
    assert state.mode == "select_complex"


@dataclass
class _FakeFetchResult:
    article_count: int = 1
    area_count: int = 1
    inactive_count: int = 0
    detail_attempted: int = 0
    detail_success: int = 0
    detail_failed: int = 0
    skipped: bool = False
    message: str = ""


class _FakeReader:
    def __init__(self, keys: list[str]) -> None:
        self._keys = list(keys)

    def __enter__(self) -> "_FakeReader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    def read_key(self) -> str:
        if self._keys:
            return self._keys.pop(0)
        return "q"


class _FakeScreen:
    def __enter__(self) -> "_FakeScreen":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


class _FakeConsole:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def clear(self) -> None:
        return None

    def print(self, *args, **kwargs) -> None:
        return None

    def screen(self, hide_cursor: bool = True) -> _FakeScreen:
        return _FakeScreen()


def test_browse_articles_recovers_when_area_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("nland.interactive.init_db", lambda _db_path: None)
    monkeypatch.setattr("nland.interactive._load_articles", lambda **kwargs: [])
    monkeypatch.setattr("nland.interactive.Console", _FakeConsole)
    monkeypatch.setattr(
        "nland.interactive.RawKeyReader",
        lambda stream: _FakeReader(["enter", "q"]),
    )

    seen_statuses: list[str] = []

    def fake_area_layout(*, area_options, state, include_inactive, min_price, max_price):
        seen_statuses.append(state.status_message)
        return "area"

    monkeypatch.setattr("nland.interactive._build_area_select_layout", fake_area_layout)

    def fail_fetch(area_name: str, config: dict[str, str | float | int]) -> _FakeFetchResult:
        raise RuntimeError("boom")

    code = browse_articles(
        db_path="/tmp/nland-interactive-test.db",
        include_inactive=False,
        min_price=None,
        max_price=None,
        area_options=[("sejong-jiphyeon-dong", {"cortar_no": "3611011800"})],
        fetch_area_callback=fail_fetch,
    )

    assert code == 0
    assert any("Fetch failed due to an unexpected error." in status for status in seen_statuses)
    assert not any("boom" in status for status in seen_statuses)


def test_browse_articles_recovers_when_refresh_fails(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("nland.interactive.init_db", lambda _db_path: None)
    monkeypatch.setattr(
        "nland.interactive._load_articles",
        lambda **kwargs: [_make_article("1", "100", "새나루1단지")],
    )
    monkeypatch.setattr("nland.interactive.Console", _FakeConsole)
    monkeypatch.setattr(
        "nland.interactive.RawKeyReader",
        lambda stream: _FakeReader(["enter", "enter", "r", "q"]),
    )

    seen_statuses: list[str] = []

    def fake_browse_layout(
        *,
        articles,
        state,
        include_inactive,
        min_price,
        max_price,
        supports_area_select,
    ):
        seen_statuses.append(state.status_message)
        return "browse"

    monkeypatch.setattr("nland.interactive._build_browse_layout", fake_browse_layout)

    call_count = 0

    def fetch_area(area_name: str, config: dict[str, str | float | int]) -> _FakeFetchResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _FakeFetchResult(message="ok")
        raise RuntimeError("refresh boom")

    code = browse_articles(
        db_path="/tmp/nland-interactive-test.db",
        include_inactive=False,
        min_price=None,
        max_price=None,
        area_options=[("sejong-jiphyeon-dong", {"cortar_no": "3611011800"})],
        fetch_area_callback=fetch_area,
    )

    assert code == 0
    assert any("Refreshing sejong-jiphyeon-dong..." in status for status in seen_statuses)
    assert any("Fetch failed due to an unexpected error." in status for status in seen_statuses)
    assert not any("refresh boom" in status for status in seen_statuses)
