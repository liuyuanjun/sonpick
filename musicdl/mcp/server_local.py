'''
Function:
    Implementation of Naive MCP Examples
Author:
    Zhenchao Jin
WeChat Official Account (微信公众号):
    Charles的皮卡丘
'''
import sys, logging
from mcp.server.fastmcp import FastMCP
from musicdl import musicdl as musicdl_pkg


'''settings'''
_client = None
mcp = FastMCP("musicdl")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)


def getclient(music_sources=None, init_music_clients_cfg=None, clients_threadings=None, requests_overrides=None, search_rules=None):
    """get music client"""
    global _client
    if _client is None:
        _client = musicdl_pkg.MusicClient(
            music_sources=music_sources or ['NeteaseMusicClient'], init_music_clients_cfg=init_music_clients_cfg or {}, clients_threadings=clients_threadings or {},
            requests_overrides=requests_overrides or {}, search_rules=search_rules or {},
        )
    return _client


@mcp.tool()
def search(keyword: str, music_sources: list[str] | None = None) -> dict:
    """Search tracks (only use content you have rights to access/download)."""
    res = getclient(music_sources=music_sources).search(keyword=keyword)
    flat = []
    for source, items in res.items():
        for i, it in enumerate(items):
            flat.append({"source": source, "index": i, "song_info": it})
    return {"results": flat}


@mcp.tool()
def download(song_infos: list[dict]) -> dict:
    """Download tracks described by song_infos."""
    getclient().download(song_infos=song_infos)
    return {"ok": True}


'''main'''
if __name__ == "__main__":
    mcp.run(transport="stdio")