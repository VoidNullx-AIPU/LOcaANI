"""Resolve a stream URL for a given episode using ani-cli.

ani-cli is invoked with a fake-mpv capture script (anicli-mpv-capture).
That script records the URL, referer, subtitle URL, and title that ani-cli
constructed, then exits. We parse the capture file. No interactive TUI,
no lockups, and the referer is read fresh from ani-cli every time — nothing
is hardcoded, so if ZokoAnime rotates domains we inherit the change for free.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Sequence

import config
from cache import get_cached, set_cached
from logger import log
from utils import StreamResult

_CAPTURE_PLAYER = str(Path(__file__).parent / "anicli-mpv-capture")

# Serialize ani-cli invocations; the capture file is a shared resource and
# ani-cli writes history/state to a shared folder.
_anicli_lock = asyncio.Lock()


def _ani_cli_path() -> Optional[str]:
    return shutil.which("ani-cli")


def _clean_title(t: str) -> str:
    t = re.sub(r"[\"'`]", "", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _run_ani_cli(title: str, ep: int, is_dub: bool, timeout: int) -> Optional[dict]:
    exe = _ani_cli_path()
    if not exe:
        log("[ANI-CLI] binary not found in PATH", "error")
        return None

    capture_file = os.path.join(
        config.CACHE_DIR, f"anicli_capture_{uuid.uuid4().hex}.json"
    )
    Path(config.CACHE_DIR).mkdir(parents=True, exist_ok=True)

    cmd = [
        exe,
        "--no-detach", "--exit-after-play",
        "-S", "1",                      # non-interactive: pick first search result
        "-e", str(ep),
    ]
    if is_dub:
        cmd.append("--dub")
    cmd.append(title)

    env = os.environ.copy()
    env["ANI_CLI_PLAYER"] = _CAPTURE_PLAYER
    env["ANI_CLI_LOG"] = "0"
    env["ANI_CLI_HIST_DIR"] = os.path.join(config.CACHE_DIR, "anicli-hist")
    env["ANICLI_CAPTURE_FILE"] = capture_file

    log(f"[ANI-CLI] Running: {' '.join(cmd)}")

    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log(f"[ANI-CLI] Timed out after {timeout}s", "warning")
        try:
            os.unlink(capture_file)
        except Exception:
            pass
        return None
    except Exception as e:
        log(f"[ANI-CLI] subprocess failed: {type(e).__name__}: {e}", "warning")
        try:
            os.unlink(capture_file)
        except Exception:
            pass
        return None

    err_lines = (proc.stderr or "").strip().splitlines()
    if proc.returncode != 0:
        last = err_lines[-1] if err_lines else ""
        log(f"[ANI-CLI] exit {proc.returncode}: {last[:200]}", "warning")

    captured = None
    try:
        with open(capture_file) as f:
            captured = json.load(f)
    except Exception:
        log("[ANI-CLI] no capture file written", "warning")
    finally:
        try:
            os.unlink(capture_file)
        except Exception:
            pass

    if not captured or not captured.get("url"):
        if err_lines:
            log(f"[ANI-CLI] stderr tail: {err_lines[-1][:200]}", "warning")
        return None

    url = captured["url"]
    referer = captured.get("referer") or ""
    sub_url = captured.get("sub_file") or ""

    subs = [{
        "url": sub_url,
        "language": "English",
        "isDefault": True,
    }] if sub_url else []

    log(f"[ANI-CLI] Resolved ep {ep} ({'dub' if is_dub else 'sub'}): {url[:100]}")
    log(f"[ANI-CLI] Referer: {referer}")

    return {
        "url": url,
        "referer": referer,
        "kind": "m3u8" if ".m3u8" in url else "mp4",
        "subtitles": subs,
    }

async def find_stream_for_episode(show_title: str, episode_num: int, is_dub: bool,
                                  alt_titles: Sequence[str] = (),
                                  server: str = "") -> Optional[StreamResult]:
    mode = "dub" if is_dub else "sub"
    key = f"{show_title.lower()}||ep{episode_num}||{mode}"

    cached = get_cached(key)
    if cached:
        log(f"[CACHE HIT] '{show_title}' Ep {episode_num} ({mode})")
        return cached

    log(f"[SOURCE] Resolving '{show_title}' ep {episode_num} ({mode})")

    candidates = [show_title, *[t for t in alt_titles if t]]
    seen = set()
    for title in candidates:
        cleaned = _clean_title(title)
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())

        async with _anicli_lock:
            result = await asyncio.to_thread(
                _run_ani_cli, cleaned, episode_num, is_dub, config.ANICLI_TIMEOUT,
            )
        if result:
            sr = StreamResult(
                url=result["url"],
                referer=result["referer"],
                kind=result["kind"],
                page_url="https://hianime.at/",
                subtitles=result["subtitles"],
                detected_mode=mode,
            )
            set_cached(key, sr)
            return sr

    log(f"[SOURCE WARNING] No stream for '{show_title}' Ep {episode_num}", "warning")
    return None
