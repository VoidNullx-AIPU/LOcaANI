from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

import requests

import config


@dataclass
class StreamResult:
    url: str
    referer: str = ""
    kind: str = "m3u8"
    page_url: str = ""
    subtitles: List[dict] = field(default_factory=list)
    detected_mode: str = ""


def origin_of(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""
    except Exception:
        return ""


def check_stream(url: str, referer: str = "", timeout: int = 6) -> bool:
    """Quick sanity probe. Returns True if the URL looks like real media."""
    headers = {"User-Agent": config.HEADERS["User-Agent"], "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
        origin = origin_of(referer)
        if origin:
            headers["Origin"] = origin
    try:
        with requests.get(url, headers=headers, timeout=timeout, stream=True) as r:
            if r.status_code not in (200, 206):
                return False
            chunk = next(r.iter_content(2048), b"")
            ctype = r.headers.get("content-type", "").lower()
            if ".m3u8" in url.lower() or "mpegurl" in ctype:
                return chunk.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#EXTM3U")
            return len(chunk) > 0 and "text/html" not in ctype
    except Exception:
        return False
