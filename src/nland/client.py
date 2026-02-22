from __future__ import annotations

import json
import time
from urllib.parse import urlencode
import urllib.request


class NaverLandClient:
    ARTICLE_LIST_URL = "https://m.land.naver.com/cluster/ajax/articleList"
    ARTICLE_DETAIL_URL = "https://fin.land.naver.com/front-api/v1/article/basicInfo"

    def __init__(
        self,
        *,
        user_agent: str = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        referer: str = "https://m.land.naver.com/",
        request_delay: float = 1.5,
        timeout: int = 10,
    ) -> None:
        self.user_agent = user_agent
        self.referer = referer
        self.request_delay = request_delay
        self.timeout = timeout

    def _request_json(self, url: str, params: dict[str, str | int | float]) -> dict:
        query = urlencode(params)
        req = urllib.request.Request(
            f"{url}?{query}",
            headers={
                "User-Agent": self.user_agent,
                "Referer": self.referer,
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8")

        data = json.loads(payload)
        code = data.get("code")
        if code not in (None, "success"):
            raise RuntimeError(f"api request failed with code={code}")
        return data

    def fetch_article_list(
        self,
        *,
        cortar_no: str = "3611011800",
        rlet_tp_cd: str = "APT",
        trad_tp_cd: str = "A1",
        lat: float = 36.499226,
        lon: float = 127.329209,
        z: int = 14,
    ) -> list[dict]:
        page = 1
        collected: list[dict] = []

        while True:
            data = self._request_json(
                self.ARTICLE_LIST_URL,
                {
                    "cortarNo": cortar_no,
                    "rletTpCd": rlet_tp_cd,
                    "tradTpCd": trad_tp_cd,
                    "lat": lat,
                    "lon": lon,
                    "z": z,
                    "page": page,
                },
            )

            body = data.get("body", [])
            if not isinstance(body, list):
                raise RuntimeError("invalid article list body")

            collected.extend(body)
            if not data.get("more"):
                break

            page += 1
            time.sleep(self.request_delay)

        return collected

    def fetch_article_detail(self, article_id: str) -> dict:
        data = self._request_json(self.ARTICLE_DETAIL_URL, {"articleId": article_id})
        if isinstance(data.get("result"), dict):
            return data["result"]
        if isinstance(data.get("body"), dict):
            return data["body"]
        return data
