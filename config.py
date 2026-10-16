import os

BASE_DIR = os.environ.get("LOCAANI_BASE_DIR", "/mnt/SSD2/Seanime")

PORT = 43222
LOG_FILE = os.path.join(BASE_DIR, "LOcaANI.log")
CACHE_FILE = os.path.join(BASE_DIR, "stream_cache.json")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

CACHE_TTL = 6 * 3600
VALIDATE_STREAMS = True

# ---- ani-cli integration --------------------------------------------------
# Referer is captured at runtime from the player invocation, nothing hardcoded.
ANICLI_TIMEOUT = 45

# Server names in provider.py that force a mode regardless of Seanime's toggle.
FORCE_DUB_SERVERS = ["dub"]
FORCE_SUB_SERVERS = ["sub"]

# ---- metadata ------------------------------------------------------------
ANILIST_ID_SOURCES = ["anilist.co", "anime.xotaku.com"]
