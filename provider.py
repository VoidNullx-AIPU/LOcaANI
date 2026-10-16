PROVIDER_CODE = """/// <reference path="./online-streaming-provider.d.ts" />

class Provider {
  private base = "http://127.0.0.1:43222/api";

  async getSettings(): Promise<Settings> {
    // Three servers so you can force sub/dub even when Seanime's own toggle
    // is disabled. "Default" follows the toggle. Quality is auto — ani-cli
    // always returns the best available.
    return {
      episodeServers: ["Default", "DUB", "SUB"],
      supportsDub: true,
    };
  }

  async search(query: SearchOptions): Promise<SearchResult[]> {
    const dubParam = query.dub ? "true" : "false";
    const url = `${this.base}/search?q=${encodeURIComponent(query.query)}&dub=${dubParam}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Search failed");
    return await res.json();
  }

  async findEpisodes(id: string): Promise<Episode[]> {
    const url = `${this.base}/episodes?id=${encodeURIComponent(id)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Episodes failed");
    return await res.json();
  }

  async findEpisodeServer(episode: EpisodeDetails, server: string): Promise<EpisodeServer> {
    const s = (server || "").toLowerCase();
    const forcedDub = /dub/.test(s);
    const forcedSub = /sub/.test(s);
    const idIsDub = episode.id.includes("||dub");
    const isDub = forcedDub ? true : forcedSub ? false : idIsDub;

    const url = `${this.base}/source?episode_id=${encodeURIComponent(episode.id)}&number=${episode.number}&title=${encodeURIComponent(episode.title || "")}&server=${encodeURIComponent(server)}&dub=${isDub ? "true" : "false"}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Source request failed");
    const data = await res.json();

    if (!data.videoSources || data.videoSources.length === 0 || !data.videoSources[0].url) {
      throw new Error(`No ${isDub ? "dubbed" : "subbed"} stream found. Try the other server.`);
    }
    return data;
  }
}
"""


def get_manifest_data() -> dict:
    return {
        "id": "Local",
        "name": "LOcaANI",
        "version": "4.0.0",
        "manifestURI": "http://127.0.0.1:43222/manifest.json",
        "language": "typescript",
        "type": "onlinestream-provider",
        "description": "Local English anime provider via ani-cli",
        "author": "Void",
        "icon": "",
        "website": "",
        "readme": "",
        "lang": "en",
        "payload": PROVIDER_CODE,
        "payloadURI": "http://127.0.0.1:43222/payload.ts",
        "plugin": {
            "version": "1",
            "permissions": {}
        }
    }
