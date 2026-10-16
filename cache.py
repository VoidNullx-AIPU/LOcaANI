import atexit
import json
import os
import shutil
import threading
import time
from dataclasses import asdict
from typing import Optional

import config
from logger import log
from utils import StreamResult

PYCACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__pycache__")

_lock = threading.RLock()
_cleaned = False


def _load() -> dict:
    if os.path.exists(config.CACHE_FILE):
        try:
            with open(config.CACHE_FILE, "r") as f:
                raw = json.load(f)
            # ignore entries from the old "key -> url string" format
            return {k: v for k, v in raw.items() if isinstance(v, dict) and "result" in v}
        except Exception as e:
            log(f"[CACHE] Error loading cache: {e}", "error")
    return {}


_data: dict = _load()


def _save():
    tmp = config.CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_data, f, indent=2)
    os.replace(tmp, config.CACHE_FILE)  # atomic: never leaves a half-written file


def _to_result(entry: dict) -> Optional[StreamResult]:
    try:
        return StreamResult(**entry["result"])
    except Exception:
        return None


def peek_cached(key: str) -> Optional[StreamResult]:
    """Return the entry even if expired (used to avoid re-picking a bad page)."""
    with _lock:
        entry = _data.get(key)
    return _to_result(entry) if entry else None


def get_cached(key: str) -> Optional[StreamResult]:
    with _lock:
        entry = _data.get(key)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > config.CACHE_TTL:
            return None
    return _to_result(entry)


def set_cached(key: str, result: StreamResult):
    with _lock:
        _data[key] = {"ts": time.time(), "result": asdict(result)}
        try:
            _save()
            log(f"[CACHE STORED] '{key}'")
        except Exception as e:
            log(f"[CACHE] Error saving cache: {e}", "error")


def drop_cached(key: str):
    with _lock:
        if _data.pop(key, None) is not None:
            try:
                _save()
            except Exception:
                pass


def clear_all_caches():
    """Delete stream_cache.json and __pycache__ (runs once, on shutdown)."""
    global _cleaned
    with _lock:
        if _cleaned:
            return
        _cleaned = True
        _data.clear()

    log("[CACHE CLEANUP] Shutting down. Cleaning cache files...")
    for path in (config.CACHE_FILE, config.CACHE_FILE + ".tmp"):
        if os.path.exists(path):
            try:
                os.remove(path)
                log(f"[CACHE CLEANUP] Removed {path}")
            except Exception as e:
                log(f"[CACHE CLEANUP] Failed to remove {path}: {e}", "error")

    if os.path.exists(PYCACHE_DIR):
        shutil.rmtree(PYCACHE_DIR, ignore_errors=True)


# Safety net for crashes. Signals (Ctrl+C / SIGTERM) are handled by uvicorn, which runs
# the app's shutdown lifespan; we deliberately do NOT override signal handlers any more
# (the old os._exit(0) handler killed uvicorn before it could close the browser cleanly).
atexit.register(clear_all_caches)
