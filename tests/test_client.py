from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from nland.client import NaverLandClient


class MockResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "MockResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


def test_fetch_article_list_sets_required_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(request, timeout: int):
        captured.update({k.lower(): v for k, v in request.header_items()})
        return MockResponse({"code": "success", "more": False, "body": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = NaverLandClient()
    client.fetch_article_list()

    assert "user-agent" in captured
    assert captured.get("referer") == "https://m.land.naver.com/"


def test_fetch_article_list_paginates_and_sleeps_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {"code": "success", "more": True, "body": [{"atclNo": "1"}]},
        {"code": "success", "more": False, "body": [{"atclNo": "2"}]},
    ]
    sleep_calls: list[float] = []

    def fake_urlopen(request, timeout: int):
        return MockResponse(responses.pop(0))

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", fake_sleep)

    client = NaverLandClient()
    articles = client.fetch_article_list()

    assert [item["atclNo"] for item in articles] == ["1", "2"]
    assert sleep_calls == [1.5]


def test_fetch_article_list_raises_for_non_success_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout: int):
        return MockResponse({"code": "fail", "body": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = NaverLandClient()
    with pytest.raises(RuntimeError):
        client.fetch_article_list()


def test_fetch_article_list_raises_for_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout: int):
        raise HTTPError(request.full_url, 500, "boom", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = NaverLandClient()
    with pytest.raises(HTTPError):
        client.fetch_article_list()


def test_fetch_article_detail_returns_result_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout: int):
        return MockResponse({"code": "success", "result": {"atclNo": "10", "prcInfo": "1억"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = NaverLandClient()
    payload = client.fetch_article_detail("10")

    assert payload["atclNo"] == "10"
