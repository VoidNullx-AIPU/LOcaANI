import sys
sys.dont_write_bytecode = True

import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import quote

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

import config
from cache import clear_all_caches
from episode_source import find_stream_for_episode
from logger import log
from metadata import get_show_info, get_skip_times
from provider import PROVIDER_CODE, get_manifest_data
from utils import origin_of


@asynccontextmanager
async def lifespan(app: FastAPI):
    log("=== Starting LOcaANI v4.0 Backend Server ===")
    yield
    clear_all_caches()


app = FastAPI(title="Local Anime Stream Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/payload.ts", response_class=PlainTextResponse)
def get_payload():
    return PROVIDER_CODE


@app.get("/manifest.json")
def get_manifest():
    return get_manifest_data()


@app.get("/api/subtitle")
def get_subtitle(u: str, r: str = ""):
    try:
        headers = {"User-Agent": config.HEADERS["User-Agent"], "Accept": "*/*"}
        if r:
            headers["Referer"] = r
            origin = origin_of(r)
            if origin:
                headers["Origin"] = origin
        rr = requests.get(u, headers=headers, timeout=8)
        if rr.status_code != 200:
            log(f"[SUBTITLE] upstream HTTP {rr.status_code}", "warning")
            return Response(status_code=rr.status_code)
        ctype = (rr.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype not in ("text/vtt", "application/x-subrip", "text/srt",
                         "application/ttml+xml", "text/plain"):
            ctype = "text/vtt"
        log(f"[SUBTITLE] served {len(rr.content)} bytes ({ctype})")
        return Response(content=rr.content, media_type=ctype)
    except Exception as e:
        log(f"[SUBTITLE] fetch failed: {type(e).__name__}: {e}", "warning")
        return Response(status_code=502)


class SearchItem(BaseModel):
    id: str
    title: str
    url: str
    subOrDub: str


class EpisodeItem(BaseModel):
    id: str
    title: str
    number: int
    url: str


class SkipInterval(BaseModel):
    start: int
    end: int


class SubtitleTrack(BaseModel):
    id: str
    url: str
    language: str
    isDefault: bool = False


class VideoSource(BaseModel):
    url: str
    quality: str = "auto"
    type: str = "m3u8"
    subtitles: Optional[List[SubtitleTrack]] = []


class ServerResponse(BaseModel):
    server: str
    headers: dict
    videoSources: List[VideoSource]
    skipIntro: Optional[SkipInterval] = None
    skipEnding: Optional[SkipInterval] = None


@app.get("/api/search", response_model=List[SearchItem])
def search(q: str, dub: bool = False):
    mode_tag = "dub" if dub else "sub"
    log(f"[API SEARCH] Query: '{q}' ({mode_tag})")
    return [{
        "id": f"{q}||{mode_tag}",
        "title": f"{q} (English {mode_tag.upper()})",
        "url": f"http://127.0.0.1:{config.PORT}/show?q={quote(q)}",
        "subOrDub": mode_tag,
    }]


@app.get("/api/episodes", response_model=List[EpisodeItem])
async def get_episodes(id: str):
    parts = id.split("||")
    show_title = parts[0]
    mode_tag = parts[1] if len(parts) > 1 else "sub"

    info = await get_show_info(show_title)
    count = info["episodes"]
    log(f"[API EPISODES] Resolved {count} episodes for '{show_title}' ({mode_tag})")

    return [{
        "id": f"{show_title}||{mode_tag}||ep{i}",
        "title": f"Episode {i}",
        "number": i,
        "url": f"http://127.0.0.1:{config.PORT}/show?q={quote(show_title)}&ep={i}",
    } for i in range(1, count + 1)]


def _server_forces_dub(server: str) -> bool:
    s = (server or "").lower()
    return any(k in s for k in config.FORCE_DUB_SERVERS)


def _server_forces_sub(server: str) -> bool:
    s = (server or "").lower()
    return any(k in s for k in config.FORCE_SUB_SERVERS)


def _build_proxied_tracks(stream, page_referer: str) -> List[SubtitleTrack]:
    proxy_base = f"http://127.0.0.1:{config.PORT}/api/subtitle"
    out: List[SubtitleTrack] = []
    for i, s in enumerate(stream.subtitles):
        u = s.get("url") or ""
        if not u:
            continue
        proxy_url = f"{proxy_base}?u={quote(u, safe='')}&r={quote(page_referer, safe='')}"
        out.append(SubtitleTrack(
            id=s.get("id") or f"en-{i}",
            url=proxy_url,
            language=s.get("language") or "English",
            isDefault=bool(s.get("isDefault")),
        ))
    return out


@app.get("/api/source", response_model=ServerResponse)
async def get_source(
    episode_id: str,
    number: int = 1,
    title: str = "",
    server: str = "Default",
    dub: bool = False,
):
    parts = episode_id.split("||")
    show_title = parts[0]

    if _server_forces_dub(server):
        is_dub = True
    elif _server_forces_sub(server):
        is_dub = False
    else:
        is_dub = dub or (len(parts) > 1 and parts[1] == "dub")

    log(f"[API SOURCE] '{show_title}' Ep {number} (Dub={is_dub}) [Server: {server}]")

    info = await get_show_info(show_title)
    alt_titles = [info.get("english", ""), info.get("romaji", ""), *info.get("synonyms", [])]
    alt_titles = [t for t in alt_titles if t]

    stream, skip = await asyncio.gather(
        find_stream_for_episode(show_title, number, is_dub, alt_titles, server),
        get_skip_times(info.get("mal_id"), number),
    )

    if not stream:
        return {"server": server, "headers": {}, "videoSources": [],
                "skipIntro": skip.get("skip_intro"), "skipEnding": skip.get("skip_ending")}

    referer = stream.referer or stream.page_url
    headers = {"User-Agent": config.HEADERS["User-Agent"], "Referer": referer}
    origin = origin_of(referer)
    if origin:
        headers["Origin"] = origin

    tracks = _build_proxied_tracks(stream, referer)

    log(f"[API SOURCE] -> {stream.kind} "
        f"({len(tracks)} subtitle track(s), mode={stream.detected_mode or 'unknown'})")

    return {
        "server": server,
        "headers": headers,
        "videoSources": [{
            "url": stream.url,
            "quality": "auto",
            "type": stream.kind,
            "subtitles": tracks,
        }],
        "skipIntro": skip.get("skip_intro"),
        "skipEnding": skip.get("skip_ending"),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT)
