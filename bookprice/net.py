from __future__ import annotations

import gzip
import http.cookiejar
import json
import urllib.parse
import urllib.request
from typing import Dict, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0"
)
TIMEOUT = 25


class Http:
    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[Dict[str, str]] = None) -> bytes:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept-Encoding": "gzip",
            **(headers or {}),
        })
        with self.opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body

    def json(self, url: str, params: Optional[dict] = None, headers: Optional[Dict[str, str]] = None):
        return json.loads(self.get(url, params, {"Accept": "application/json", **(headers or {})}))

    def cookie(self, name: str) -> Optional[str]:
        for c in self.jar:
            if c.name == name:
                return urllib.parse.unquote(c.value)
        return None
