# LOcaANI

A local anime streaming provider for [Seanime](https://seanime.app). Runs a small FastAPI backend on `127.0.0.1:43222` that Seanime's online-stream provider talks to. Streams are resolved by calling [`ani-cli`](https://github.com/pystardust/ani-cli) with a fake-mpv capture script, so the whole pipeline runs headless — no browser, no ads, no interactive menus.

## Status

**Working.** Sub and dub streams resolve in ~10 seconds on the first call, instant after that thanks to caching. Subtitles load through a local proxy that handles the CDN's referer requirements. AniList handles metadata, AniSkip handles skip-intro/skip-outro.

## What it does

- **Search**: passes the query to Seanime, which forwards to AniList for the canonical title + episode count
- **Episodes**: AniList episode count, with `nextAiringEpisode` handling for currently-airing shows
- **Streams**: `ani-cli --no-detach --exit-after-play -S 1 -e <N> [--dub] "<title>"` with a fake `mpv` on `$PATH` that captures the URL, referer, subtitle URL, and title to a JSON file, then exits cleanly
- **Subtitles**: proxied through `GET /api/subtitle?u=<url>&r=<referer>` so mpv can fetch them without needing to send the CDN's referer itself
- **Skip times**: AniSkip v2, using AniList's `idMal`

## Architecture

Seanime
↓ (HTTP)
provider.py ← TypeScript plugin, runs inside Seanime
↓
ANIserver.py ← FastAPI backend, port 43222
↓
episode_source.py ← resolves the stream
↓
ani-cli ← subprocess, one per uncached request
↓
anicli-mpv-capture ← fake player, captures URL + referer, exits 0


Nothing runs in a browser. There is no Playwright, no SearXNG, no HTML parsing. If ani-cli stops working, the whole thing stops.

## Requirements

- **Python 3.11+** with `fastapi`, `uvicorn`, `pydantic`, `requests` (all in Arch repos as `python-fastapi`, etc.)
- **`ani-cli` v5.1.0 or newer** — `yay -S ani-cli` on Arch, or build from source. Must include the `-S` / `--select-nth` flag and the `debug` player mode. Older versions will not work.
- **`fzf`** — ani-cli's dependency check requires it even when we never open the menu
- **Seanime** installed and running locally

## Install

```bash
git clone https://github.com/VoidNullx-AIPU/LOcaANI.git
cd LOcaANI
```
Copy the files into your Seanime folder. The backend expects to live next to the seanime binary — usually a dedicated folder like /mnt/SSD2/Seanime or ~/.seanime. or the bin folder

# Default location
```bash
cp *.py anicli-mpv-capture ~/.local/bin/seanime
# or
cp *.py anicli-mpv-capture /bin/seanime
# would recommend not putting it inside the shared root
```
Edit config.py if your Seanime folder is somewhere else:
```python
BASE_DIR = os.environ.get("LOCAANI_BASE_DIR", "Seanime location")
```
Make the capture script executable:
```bash
chmod +x /mnt/SSD2/Seanime/anicli-mpv-capture
```
Start the backend:
```bash
./wherever/it/is/selocal.sh
```
Then in Seanime: Settings → Extensions → Install from URL and enter http://127.0.0.1:43222/manifest.json.
If you already have the extension installed, click Reload after restarting the backend — the server names in the picker will update.

**Usage**
In Seanime's stream picker you'll see three servers:

| Server | Behaviour |
|---|---|
| Default | Follows Seanime's sub/dub toggle |
| DUB | Forces dub regardless of the toggle |
| SUB | Forces sub regardless of the toggle |

Quality is auto — ani-cli already serves the best available variant from the source. There's no quality picker.

Skip Intro / Skip Ending buttons appear automatically when AniSkip has data for the episode.

**Configuration**
All in `config.py` The knobs you'll actually touch:
```python
PORT = 43222                  # backend port
BASE_DIR = "..."              # where Seanime lives
LOG_FILE = "Locaanime.log"    # rotation is 1MB × 2 backups
CACHE_TTL = 6 * 3600          # how long to trust a resolved stream URL
ANICLI_TIMEOUT = 45           # seconds per ani-cli call
```
**How the referer capture works**

The trick that makes this work headless is anicli-mpv-capture. ani-cli constructs a command line that looks like:
```bash
mpv --referrer=https://zokoanime.video/ --sub-file=https://...vtt --force-media-title="..." https://....m3u8
```
Our fake mpv script intercepts those arguments, writes them to a JSON file, and exits with status 0. ani-cli sees a successful player exit, cleans up, and exits itself. We then read the JSON to get the referer ani-cli actually used — nothing is hardcoded, so if the embed host rotates to a new domain, we inherit the change for free.

**Known limitations**

1. ani-cli is a hard dependency. If it breaks, this project breaks. See Roadmap.

2. Single upstream source. ani-cli currently scrapes hianime.at. If that site goes down, so does the resolution. There's no fallback provider yet.

3. Sub/dub depends on the site's own labelling. Some sites mark a stream as "dub" but serve the subbed audio. Nothing in the code can detect that.

4. Episodes must exist on the site — AniList may know about an episode that hianime hasn't published yet. The resolver returns nothing in that case.

5. No offline mode. This is a client for upstream streaming, not a downloader.

**Roadmap**
The current pipeline works but has two structural weaknesses: it depends on `ani-cli` being installed and maintained on the user's machine, and it depends on ani-cli's single-source scraper remaining functional. Both of those have failed in the past year. The long-term goal is to remove both.

**Milestone 1 — Native scraping (primary goal)**
Replace the ani-cli subprocess with our own scraper built into episode_source.py. Same HTTP requests ani-cli makes (search → episode list → server list → embed page → deobfuscate → m3u8), but:

    Pure Python, no external binary required

    We control the parsing, so version drift in ani-cli doesn't affect us

    We can port the XOR deobfuscation directly — it's ~15 lines

    Uses curl-impersonate for Cloudflare TLS fingerprint evasion where plain requests fails

This is the highest-value change. It eliminates the "user must have ani-cli installed" requirement and the "ani-cli maintainer merged a bad commit" risk in one move.

**Milestone 2 — Multiple providers**
Once our own scraper exists, add more upstream sources. allanime, animepahe, 9anime clones — anything with a stable API or predictable HTML. Try them in order until one returns a stream. This is what "systemcall moving" actually looks like: multiple sources behind one interface, so no single site going down takes the whole thing with it.

**Milestone 3 — Fallback to browser scraping**
Last resort for shows the API-based sources don't have. A trimmed Playwright pipeline that reads the player from any site with a <video> element. Slow and fragile, but it catches the long tail. Only worth building after Milestones 1 and 2 prove reliable enough that we rarely need it.

**Milestone 4 — Quality selection**
ani-cli auto-picks the best quality. Once we own the scraper, expose the master playlist's variants to Seanime so the user can drop to 720p when 1080p stutters, or lock to a specific bitrate on metered connections.

**File map**
| File | Job |
|---|---|
| `ANIserver.py` | FastAPI app, HTTP routes Seanime calls |
| `episode_source.py` | Resolves a stream by calling ani-cli headless |
| `anicli-mpv-capture` | Fake `mpv` that logs the URLs ani-cli passes to it |
| `provider.py` | TypeScript shim Seanime loads, defines server list |
| `metadata.py` | AniList lookups + AniSkip skip times |
| `cache.py` | JSON-file cache for resolved streams, cleared on shutdown |
| `utils.py` | `StreamResult` dataclass, `check_stream` probe, `origin_of` helper |
| `logger.py` | Rotating file + console logger |
| `config.py` | All tunables |

**Credits**
- [`ani-cli`](https://github.com/pystardust/ani-cli) by pystardust — the stream resolution logic this project wraps
- [`Seanime`](https://github.com/5rahim/seanime) by 5rahim — the media server this plugs into
- [AniList](https://anilist.co) — metadata
- [AniSkip](https://api.aniskip.com) — skip-intro/skip-outro timestamps

