import asyncio
import time
from typing import Optional

import requests

import config
from logger import log

_ANILIST_QUERY = """
query ($search: String) {
  Media (search: $search, type: ANIME) {
    id
    idMal
    episodes
    status
    nextAiringEpisode { episode }
    synonyms
    title { romaji english }
  }
}
"""

_SHOW_TTL = 3600
_SKIP_TTL = 6 * 3600
_FAIL_TTL = 60

_show_cache: dict = {}
_skip_cache: dict = {}


def _fetch_show(title: str) -> dict:
    info = {"ok": False, "episodes": 12, "romaji": title, "english": "",
            "synonyms": [], "mal_id": None}
    try:
        r = requests.post(
            "https://graphql.anilist.co",
            json={"query": _ANILIST_QUERY, "variables": {"search": title}},
            headers={
                "User-Agent": config.HEADERS["User-Agent"],
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=5,
        )
        if r.status_code != 200:
            log(f"[METADATA] AniList HTTP {r.status_code} for '{title[:80]}'", "warning")
            return info
        media = (r.json().get("data") or {}).get("Media")
        if not media:
            return info

        nxt = (media.get("nextAiringEpisode") or {}).get("episode")
        info["episodes"] = max(1, nxt - 1) if nxt else (media.get("episodes") or 12)
        titles = media.get("title") or {}
        info["romaji"] = titles.get("romaji") or title
        info["english"] = titles.get("english") or ""
        info["synonyms"] = [s for s in (media.get("synonyms") or [])
                            if s and s.isascii()][:3]
        info["mal_id"] = media.get("idMal")
        info["ok"] = True
    except Exception as e:
        log(f"[METADATA] AniList lookup skipped: {e}", "warning")
    return info


def _fetch_skip(mal_id: int, episode: int) -> dict:
    out = {"skip_intro": None, "skip_ending": None}
    try:
        r = requests.get(
            f"https://api.aniskip.com/v2/skip-times/{mal_id}/{episode}",
            params=[("types", "op"), ("types", "ed"), ("episodeLength", 0)],
            headers={"User-Agent": config.HEADERS["User-Agent"],
                     "Accept": "application/json"},
            timeout=4,
        )
        if r.status_code == 200:
            for item in r.json().get("results", []):
                iv = item.get("interval", {})
                span = {"start": int(iv.get("startTime", 0)),
                        "end": int(iv.get("endTime", 0))}
                if item.get("skipType") == "op":
                    out["skip_intro"] = span
                elif item.get("skipType") == "ed":
                    out["skip_ending"] = span
    except Exception as e:
        log(f"[METADATA] AniSkip query skipped: {e}", "warning")
    return out


async def get_show_info(title: str) -> dict:
    key = title.strip().lower()
    hit = _show_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    info = await asyncio.to_thread(_fetch_show, title)
    _show_cache[key] = (time.time() + (_SHOW_TTL if info["ok"] else _FAIL_TTL), info)
    return info


async def get_skip_times(mal_id: Optional[int], episode: int) -> dict:
    if not mal_id:
        return {"skip_intro": None, "skip_ending": None}
    key = (mal_id, episode)
    hit = _skip_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    skip = await asyncio.to_thread(_fetch_skip, mal_id, episode)
    _skip_cache[key] = (time.time() + _SKIP_TTL, skip)
    return skip
