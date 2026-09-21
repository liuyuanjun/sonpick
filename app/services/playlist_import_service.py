"""歌单链接轻量导入：只拉曲目元数据（每源 1 个列表请求 + 分页），不做逐曲下载地址解析。

与轻量搜索同哲学（解析前置）：导入只回答「这个歌单有哪些歌」——曲目自带平台
song_id，导入后由 worker 按 song_id 锁定、下载时才解析格式与地址。
故意不调用 musicdl 的 ``parseplaylist``：它对每首曲目串行跑完整解析级联
（第三方 + 官方，每首数个请求），百首歌单就是数百个串行请求。

六源歌单接口与字段形状（2026-09 实测）：
- QQ：fcg_ucc_getcdinfo_byids_cp.fcg → cdlist[0].songlist（songmid/songname/singer/albumname），
  部分歌单返回 subcode=4000「check privacy error!」（平台侧限制，原样提示）
- 网易：api/v6/playlist/detail 只给 trackIds，需 api/v3/song/detail 批量取元数据（≤500/批）
- 咪咕：playlist/song/v2.0 分页 50 → songList（songName/singerList/contentId/audioFormats），
  歌单名走 resource/playlist/v2.0 → data.title
- 酷狗：get_other_list_file 分页 300（手机端形状：name=「歌手 - 歌名」、hash、timelen 毫秒），
  歌单名走 api/v3/special/info → specialname；链接必须是 …/special/single/{id} 形式
- 酷我：playListInfo 分页 100 → musicList（musicrid/name/artist/album 全小写）
- 千千：v1/tracklist/info 分页 50（需 _addsignandtstoparams 签名）→ trackList（与搜索同形状）
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlsplit

from musicdl.modules.sources.kugou import KUGOU_MUSIC_HOSTS
from musicdl.modules.sources.kuwo import KUWO_MUSIC_HOSTS
from musicdl.modules.sources.migu import MIGU_MUSIC_HOSTS
from musicdl.modules.sources.netease import NETEASE_MUSIC_HOSTS
from musicdl.modules.sources.qianqian import QIANQIAN_MUSIC_HOSTS
from musicdl.modules.sources.qq import QQ_MUSIC_HOSTS
from musicdl.modules.utils import SongInfo, resp2json, safeextractfromdict

from app.services.light_search_service import (
    _LIGHT_CLIENTS,
    _REQUEST_TIMEOUT,
    SOURCE_LABELS,
    _hms,
    _int_or_none,
    _legalize,
    _new_client,
    migu_item_to_songinfo,
    netease_item_to_songinfo,
    qianqian_item_to_songinfo,
    qq_item_to_songinfo,
    register_songs,
)

log = logging.getLogger("sonpick.playlist")

_MAX_PAGES = 40  # 分页安全上限（每页 50~300，足够覆盖万首级歌单）

_SOURCE_HOSTS = {
    "QQMusicClient": QQ_MUSIC_HOSTS,
    "NeteaseMusicClient": NETEASE_MUSIC_HOSTS,
    "MiguMusicClient": MIGU_MUSIC_HOSTS,
    "KugouMusicClient": KUGOU_MUSIC_HOSTS,
    "KuwoMusicClient": KUWO_MUSIC_HOSTS,
    "QianqianMusicClient": QIANQIAN_MUSIC_HOSTS,
}


def _host_matches(hostname: str, hosts: set) -> bool:
    hostname = (hostname or "").lower()
    return any(hostname == h or hostname.endswith("." + h) for h in hosts)


def _extract_playlist_id(url: str, source: str) -> Optional[str]:
    """按 musicdl parseplaylist 的同款规则提取歌单 ID：query/fragment 优先，路径末段兜底。"""
    parsed = urlparse(url)
    for query_text in (parsed.query, urlsplit(parsed.fragment).query, urlparse(parsed.fragment).query):
        for key in ("id", "playlistId", "playlist_id", "pid", "dissid", "specialid"):
            values = parse_qs(query_text).get(key)
            if values and values[0]:
                return values[0]
    tail = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else ""
    tail = tail.removesuffix(".html").removesuffix(".htm")
    return tail or None


def detect_playlist_source(url: str) -> Optional[str]:
    """按 URL 主机名识别平台；识别不了返回 None。"""
    hostname = (urlparse(url).hostname or "").lower()
    for src, hosts in _SOURCE_HOSTS.items():
        if _host_matches(hostname, hosts):
            return src
    return None


# ---------------------------------------------------------------- 各源曲目拉取


def _fetch_qq(client, playlist_id: str) -> tuple[str, list[dict]]:
    resp = client.get(
        "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg",
        headers={"Referer": f"https://y.qq.com/n/ryqq/playlist/{playlist_id}"},
        params={"disstid": str(playlist_id), "type": "1", "json": "1", "utf8": "1", "onlysong": "0", "format": "json"},
        timeout=_REQUEST_TIMEOUT,
    )
    body = resp2json(resp)
    if body.get("code") != 0 or not (body.get("cdlist") or [{}])[0].get("songlist"):
        raise ValueError(f"QQ 音乐歌单拉取失败：{body.get('msg') or '未知错误'}")
    cdlist = body["cdlist"][0]
    tracks = cdlist.get("songlist") or cdlist.get("list") or []
    return _legalize(cdlist.get("dissname") or ""), tracks


def _fetch_netease(client, playlist_id: str) -> tuple[str, list[dict]]:
    resp = client.post("https://music.163.com/api/v6/playlist/detail", data={"id": playlist_id}, timeout=_REQUEST_TIMEOUT)
    body = resp2json(resp)
    playlist = body.get("playlist") or {}
    track_ids = [t.get("id") for t in (playlist.get("trackIds") or []) if t.get("id")]
    if not track_ids:
        raise ValueError("网易云音乐歌单为空或不存在")
    name = _legalize(playlist.get("name") or "")
    # trackIds 只有 ID，需批量取元数据；响应顺序不可靠，按 trackIds 顺序重排
    by_id: dict[str, dict] = {}
    for start in range(0, len(track_ids), 500):
        chunk = track_ids[start : start + 500]
        resp = client.post(
            "https://music.163.com/api/v3/song/detail",
            data={"c": json.dumps([{"id": i} for i in chunk])},
            timeout=_REQUEST_TIMEOUT,
        )
        for song in (resp2json(resp).get("songs") or []):
            if song.get("id"):
                by_id[str(song["id"])] = song
    return name, [by_id[str(i)] for i in track_ids if str(i) in by_id]


def _fetch_migu(client, playlist_id: str) -> tuple[str, list[dict]]:
    tracks: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        resp = client.get(
            f"https://app.c.nf.migu.cn/MIGUM3.0/resource/playlist/song/v2.0?pageNo={page}&pageSize=50&playlistId={playlist_id}",
            timeout=_REQUEST_TIMEOUT,
        )
        data = safeextractfromdict(resp2json(resp), ["data"], {}) or {}
        batch = data.get("songList") or []
        if not batch:
            break
        tracks.extend(batch)
        if float(data.get("totalCount") or 0) <= len(tracks):
            break
    # 按 contentId 去重（咪咕分页可能重复返回）
    tracks = list({t["contentId"]: t for t in tracks if t.get("contentId")}.values())
    if not tracks:
        raise ValueError("咪咕音乐歌单为空或不存在")
    name = ""
    try:
        resp = client.get(f"https://app.c.nf.migu.cn/resource/playlist/v2.0?playlistId={playlist_id}", timeout=_REQUEST_TIMEOUT)
        name = _legalize(safeextractfromdict(resp2json(resp), ["data", "title"], "") or "")
    except Exception as exc:
        log.info("咪咕歌单名获取失败 playlist=%s err=%s", playlist_id, exc)
    return name, tracks


def _kugou_signature(api_url: str) -> str:
    """musicdl parseplaylist 同款签名（盐 + 排序后的 query 参数拼接 + 盐的 md5）。"""
    salt = "OIlwieks28dk2k092lksi2UIkp"
    raw = salt + "".join(sorted(str(api_url).split("?", 1)[1].split("&"))) + salt
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _fetch_kugou(client, playlist_id: str) -> tuple[str, list[dict]]:
    headers = {
        "User-Agent": "Android9-AndroidPhone-11239-18-0-playlist-wifi",
        "Host": "gatewayretry.kugou.com",
        "x-router": "pubsongscdn.kugou.com",
        "mid": "239526275778893399526700786998289824956",
        "dfid": "-",
        "clienttime": str(time.time()).split(".")[0],
    }
    tracks: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        api_url = (
            f"http://gatewayretry.kugou.com/v2/get_other_list_file?specialid={playlist_id}&need_sort=1"
            f"&module=CloudMusic&clientver=11239&pagesize=300&specalidpgc={playlist_id}&userid=0"
            f"&page={page}&type=0&area_code=1&appid=1005"
        )
        resp = client.get(api_url + "&signature=" + _kugou_signature(api_url), headers=headers, timeout=_REQUEST_TIMEOUT)
        data = safeextractfromdict(resp2json(resp), ["data"], {}) or {}
        batch = data.get("info") or []
        if not batch:
            break
        tracks.extend(batch)
        if float(data.get("count") or 0) <= len(tracks):
            break
    tracks = list({t["hash"]: t for t in tracks if t.get("hash")}.values())
    if not tracks:
        raise ValueError("酷狗音乐歌单为空或不存在（链接需为 kugou.com/…/special/single/{id} 形式）")
    name = ""
    try:
        resp = client.get(f"http://mobilecdnbj.kugou.com/api/v3/special/info?specialid={playlist_id}", timeout=_REQUEST_TIMEOUT)
        name = _legalize(safeextractfromdict(resp2json(resp), ["data", "specialname"], "") or "")
    except Exception as exc:
        log.info("酷狗歌单名获取失败 playlist=%s err=%s", playlist_id, exc)
    return name, tracks


def _fetch_kuwo(client, playlist_id: str) -> tuple[str, list[dict]]:
    tracks: list[dict] = []
    name = ""
    for page in range(1, _MAX_PAGES + 1):
        resp = client.get(
            f"https://m.kuwo.cn/newh5app/wapi/api/www/playlist/playListInfo?pid={playlist_id}&pn={page}&rn=100",
            timeout=_REQUEST_TIMEOUT,
        )
        data = safeextractfromdict(resp2json(resp), ["data"], {}) or {}
        batch = data.get("musicList") or []
        if not batch:
            break
        if not name:
            name = _legalize(data.get("name") or "")
        tracks.extend(batch)
        if float(data.get("total") or 0) <= len(tracks):
            break
    # 酷我曲目主键 musicrid 大小写不敏感，统一小写去重
    tracks = list({str(t.get("musicrid") or "").lower(): t for t in tracks if t.get("musicrid")}.values())
    if not tracks:
        raise ValueError("酷我音乐歌单为空或不存在")
    return name, tracks


def _fetch_qianqian(client, playlist_id: str) -> tuple[str, list[dict]]:
    tracks: list[dict] = []
    name = ""
    for page in range(1, _MAX_PAGES + 1):
        params = client._addsignandtstoparams(  # 私有签名方法（钉版依赖，契约测试兜底）
            params={"pageNo": page, "pageSize": 50, "appid": client.APPID, "id": playlist_id}
        )
        resp = client.get("https://music.91q.com/v1/tracklist/info", params=params, timeout=_REQUEST_TIMEOUT)
        data = safeextractfromdict(resp2json(resp), ["data"], {}) or {}
        batch = data.get("trackList") or []
        if not batch:
            break
        if not name:
            name = _legalize(data.get("title") or "")
        tracks.extend(batch)
        if float(data.get("trackCount") or 0) <= len(tracks):
            break
    tracks = list({str(t["TSID"]): t for t in tracks if t.get("TSID")}.values())
    if not tracks:
        raise ValueError("千千音乐歌单为空或不存在")
    return name, tracks


# ---------------------------------------------------------------- 形状适配（与搜索不同的源）


def _kugou_playlist_item_to_songinfo(item: dict) -> Optional[SongInfo]:
    """酷狗歌单（手机端）条目 → SongInfo：name 是「歌手 - 歌名」合写，时长单位毫秒，主键是 hash。"""
    file_hash = item.get("hash")
    if not file_hash:
        return None
    full_name = str(item.get("name") or "")
    if " - " in full_name:
        singers, song_name = full_name.split(" - ", 1)
    else:
        singers, song_name = str(item.get("singername") or ""), full_name
    album = safeextractfromdict(item, ["albuminfo", "name"], "") or ""
    timelen = _int_or_none(item.get("timelen"))
    duration_s = int(timelen / 1000) if timelen and timelen > 1000 else timelen
    cover = str(item.get("cover") or "")
    if "{size}" in cover:
        cover = cover.replace("{size}", "480")
    song = SongInfo(
        source="KugouMusicClient",
        raw_data={"search": item, "download": {}, "lyric": {}},
        song_name=_legalize(song_name.strip()),
        singers=_legalize(singers.strip()),
        album=_legalize(album),
        duration_s=duration_s,
        duration=_hms(duration_s),
        cover_url=cover or None,
        identifier=str(file_hash),
    )
    song.formats_meta = []
    return song


def _kuwo_playlist_item_to_songinfo(item: dict) -> Optional[SongInfo]:
    """酷我歌单条目 → SongInfo：键全小写（musicrid/name/artist/album/duration），无 MINFO 码率表。"""
    rid = item.get("musicrid")
    if not rid:
        return None
    duration_s = _int_or_none(item.get("duration"))
    song = SongInfo(
        source="KuwoMusicClient",
        raw_data={"search": item, "download": {}, "lyric": {}},
        song_name=_legalize(item.get("name") or ""),
        singers=_legalize(item.get("artist") or ""),
        album=_legalize(item.get("album") or ""),
        duration_s=duration_s,
        duration=_hms(duration_s),
        cover_url=item.get("pic") or None,
        identifier=str(rid),
    )
    song.formats_meta = []
    return song


_FETCHERS = {
    "QQMusicClient": (_fetch_qq, qq_item_to_songinfo),
    "NeteaseMusicClient": (_fetch_netease, netease_item_to_songinfo),
    "MiguMusicClient": (_fetch_migu, migu_item_to_songinfo),
    "KugouMusicClient": (_fetch_kugou, _kugou_playlist_item_to_songinfo),
    "KuwoMusicClient": (_fetch_kuwo, _kuwo_playlist_item_to_songinfo),
    "QianqianMusicClient": (_fetch_qianqian, qianqian_item_to_songinfo),
}


def parse_playlist(url: str) -> dict:
    """解析歌单链接 → {source, playlist_id, name, tracks: [SongInfo]}（只取元数据）。"""
    url = (url or "").strip()
    if not url.startswith("http"):
        raise ValueError("请输入完整的歌单链接（http/https 开头）")
    source = detect_playlist_source(url)
    if source is None:
        # 短链/分享链接先跟随一次重定向再识别
        try:
            client = _new_client(_LIGHT_CLIENTS, "QQMusicClient")
            url = client.session.head(url, allow_redirects=True, timeout=_REQUEST_TIMEOUT).url
            source = detect_playlist_source(url)
        except Exception as exc:
            log.info("歌单链接重定向解析失败 url=%s err=%s", url, exc)
    if source is None or source not in _FETCHERS:
        raise ValueError("不支持的歌单链接：目前支持 QQ/网易/咪咕/酷狗/酷我/千千的歌单地址")
    playlist_id = _extract_playlist_id(url, source)
    if not playlist_id:
        raise ValueError(f"无法从链接中识别{SOURCE_LABELS.get(source, source)}歌单 ID")
    fetcher, mapper = _FETCHERS[source]
    client = _new_client(_LIGHT_CLIENTS, source)
    name, raw_tracks = fetcher(client, playlist_id)
    tracks: list[SongInfo] = []
    for raw in raw_tracks:
        try:
            song = mapper(raw)
        except Exception as exc:
            log.info("歌单条目解析失败 src=%s err=%s", source, exc)
            continue
        if song is not None:
            song._sonpick_source = source
            tracks.append(song)
    if not tracks:
        raise ValueError("歌单曲目解析失败，请换个链接试试")
    # 按 (source, identifier) 去重（QQ 等源的歌单列表可能重复返回同一曲目）
    unique: list[SongInfo] = []
    seen: set[str] = set()
    for song in tracks:
        if song.identifier in seen:
            continue
        seen.add(song.identifier)
        unique.append(song)
    tracks = unique
    # 注册进歌曲注册表：worker 下载时按 (source, song_id) 直接锁定，无需重新搜索
    register_songs(tracks)
    return {"source": source, "playlist_id": str(playlist_id), "name": name or f"歌单 {playlist_id}", "tracks": tracks}
