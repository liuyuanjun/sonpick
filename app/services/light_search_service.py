"""轻量音乐搜索与下载地址解析（搜索/解耦架构的核心）。

与 musicdl 原生搜索的区别：musicdl 的 ``client.search()`` 会在搜索期为
每条结果逐个解析下载地址（第三方 API 级联 + 官方逐音质请求 + 逐条链接
探测），单次搜索可达几十上百次串行 HTTP。本模块把「搜索」与「解析」拆开：

1. ``search``：只发搜索请求本身，从响应直接提取元数据（歌名/歌手/专辑/
   时长/封面/平台可得格式），每源一次请求，源间并发，总耗时 ≈ 1s。
2. ``resolve_formats`` / ``resolve_for_download``：用户锁定某一首后，按音质
   档位定向解析并探测链接（每档 1 次接口请求 + 1 次探测），得到「已验证
   可下」的格式列表；下载时只为被选中的那一首做一次解析。

协议实现（请求构造、网易 eapi 加密、咪咕响应解密、链接探测、第三方解析
级联、下载落盘）全部复用 musicdl，仅跳过其搜索期的逐条解析。musicdl 为
精确钉版依赖；用到的私有方法（``_decryptresp``、``_parsewiththirdpartapis``、
``audio_link_tester`` 等）由 tests/test_light_search.py 的契约测试兜底，
上游升级导致签名漂移时测试会直接失败。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import as_completed
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from musicdl.modules.sources import MiguMusicClient, NeteaseMusicClient, QQMusicClient
from musicdl.modules.utils import (
    AudioLinkTester,
    SongInfo,
    SongInfoUtils,
    legalizestring,
    resp2json,
    safeextractfromdict,
)
from musicdl.modules.utils.neteaseutils import EapiCryptoUtils
from musicdl.modules.utils.qqutils import Credential, QQMusicClientUtils

from app.services.execution import run_with_hard_timeout, submit as executor_submit

log = logging.getLogger("sonpick.search")

# ---------------------------------------------------------------- 常量

DEFAULT_DOWNLOAD_SOURCES = [
    "QQMusicClient",
    "NeteaseMusicClient",
    "MiguMusicClient",
]
SOURCE_LABELS = {
    "QQMusicClient": "QQ 音乐",
    "NeteaseMusicClient": "网易云音乐",
    "MiguMusicClient": "咪咕音乐",
}
# 轻量搜索每源结果数：一次请求一页，成本与条数无关，取与前端页大小一致
DEFAULT_SEARCH_SIZE_PER_SOURCE = 20
# 单源搜索硬超时兜底（请求本身已带 timeout，这里仅防 musicdl 内部重试叠加）
LIGHT_SEARCH_TIMEOUT_SECONDS = 30
# 第三方解析级联硬超时：仅下载兜底路径使用
THIRD_PARTY_TIMEOUT_SECONDS = 45

# 音质档位：解析/下载统一的三档语义
TIERS = ("lossless", "high", "standard")
TIER_LABELS = {"lossless": "无损", "high": "高品质", "standard": "标准"}
# 批量下载 prefer（历史语义）→ 档位
PREFER_TO_TIER = {"flac": "lossless", "mp3": "high", "m4a": "high", "any": "best"}

# QQ：档位 → 官方 vkey 文件类型（SongFileType 子集，按目标格式精确请求）
_QQ_TIER_FILETYPES = {
    "lossless": [("F000", ".flac")],
    "high": [("M800", ".mp3")],
    "standard": [("M500", ".mp3")],
}
# QQ：搜索响应 file.size_* → 平台可得格式（展示用，按音质从高到低）
_QQ_SIZE_FIELDS = [
    ("size_hires", "flac", "lossless", "Hi-Res"),
    ("size_flac", "flac", "lossless", "FLAC"),
    ("size_ape", "ape", "lossless", "APE"),
    ("size_320mp3", "mp3", "high", "320K"),
    ("size_192ogg", "ogg", "high", "OGG"),
    ("size_128mp3", "mp3", "standard", "128K"),
    ("size_96ogg", "ogg", "standard", "OGG"),
]

# 网易：档位 → eapi level
_NETEASE_TIER_LEVELS = {"lossless": "lossless", "high": "exhigh", "standard": "standard"}
_NETEASE_EAPI_URL = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"

# 咪咕：formatType → (ext, 档位)；Z3D 为加密格式，musicdl 同样跳过
_MIGU_FORMAT_TIERS = {
    "ZQ24": ("flac", "lossless"), "ZQ32": ("flac", "lossless"),
    "SQ": ("flac", "lossless"), "ZQ": ("flac", "lossless"),
    "HQ": ("mp3", "high"),
    "PQ": ("mp3", "standard"), "LQ": ("mp3", "standard"),
}
_MIGU_LISTEN_URL = "https://c.musicapp.migu.cn/strategy/listen-url/h5/v2.4"

_REQUEST_TIMEOUT = (5, 12)
_WORK_DIR = Path("/tmp/musicdl_light")

# ---------------------------------------------------------------- 结果缓存

_CACHE_TTL_SECONDS = 600


class _TTLCache:
    """进程内 TTL 缓存（单用户单进程部署模型，线程安全即可）。"""

    def __init__(self, ttl: float = _CACHE_TTL_SECONDS):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            ts, value = entry
            if time.monotonic() - ts > self.ttl:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key, value) -> None:
        with self._lock:
            # 简单容量护栏：超过 256 项时清空过期项，仍超则全清
            if len(self._data) >= 256:
                now = time.monotonic()
                self._data = {k: v for k, v in self._data.items() if now - v[0] <= self.ttl}
                if len(self._data) >= 256:
                    self._data.clear()
            self._data[key] = (time.monotonic(), value)


# ---------------------------------------------------------------- 元数据提取（纯函数，契约测试直接覆盖）

def _hms(seconds) -> Optional[str]:
    try:
        n = int(float(seconds))
    except Exception:
        return None
    return SongInfoUtils.seconds2hms(n) if n > 0 else None


def _int_or_none(value) -> Optional[int]:
    try:
        n = int(float(value))
        return n if n > 0 else None
    except Exception:
        return None


def qq_item_to_songinfo(item: dict) -> Optional[SongInfo]:
    """QQ item_song 条目 → 纯元数据 SongInfo（不解析下载地址）。"""
    mid = item.get("mid") or item.get("songmid")
    if not mid:
        return None
    duration_s = _int_or_none(item.get("interval"))
    file_meta = item.get("file") or {}
    formats: list[dict] = []
    for size_key, ext, tier, label in _QQ_SIZE_FIELDS:
        size = _int_or_none(file_meta.get(size_key))
        if size:
            formats.append({"ext": ext, "size_bytes": size, "quality": tier, "label": label})
    # QQ 搜索接口对付费曲目也返回 size（平台有此格式）；不做 VIP/版权预判，能不能下由下载时验证决定
    albummid = safeextractfromdict(item, ["album", "mid"], "") or item.get("albummid") or ""
    best = formats[0] if formats else {}
    song = SongInfo(
        source=QQMusicClient.source,
        raw_data={"search": item, "download": {}, "lyric": {}},
        song_name=legalizestring(item.get("title") or item.get("songname") or ""),
        singers=legalizestring(", ".join(
            s.get("name") for s in (item.get("singer") or []) if isinstance(s, dict) and s.get("name")
        )),
        album=legalizestring(safeextractfromdict(item, ["album", "title"], None) or item.get("albumname") or ""),
        ext=best.get("ext"),
        file_size_bytes=best.get("size_bytes"),
        file_size=SongInfoUtils.byte2mb(best["size_bytes"]) if best.get("size_bytes") else None,
        duration_s=duration_s,
        duration=_hms(duration_s),
        cover_url=f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{albummid}.jpg" if albummid else None,
        identifier=str(mid),
    )
    song.formats_meta = formats
    return song


def netease_item_to_songinfo(item: dict) -> Optional[SongInfo]:
    """网易 cloudsearch 条目 → 纯元数据 SongInfo（无文件大小信息）。"""
    song_id = item.get("id")
    if not song_id:
        return None
    duration_s = _int_or_none((item.get("dt") or 0) / 1000 if item.get("dt") else None)
    song = SongInfo(
        source=NeteaseMusicClient.source,
        raw_data={"search": item, "download": {}, "lyric": {}},
        song_name=legalizestring(item.get("name") or ""),
        singers=legalizestring(", ".join(
            s.get("name") for s in (item.get("ar") or []) if isinstance(s, dict) and s.get("name")
        )),
        album=legalizestring(safeextractfromdict(item, ["al", "name"], None) or ""),
        duration_s=duration_s,
        duration=_hms(duration_s),
        cover_url=safeextractfromdict(item, ["al", "picUrl"], None),
        identifier=str(song_id),
    )
    song.formats_meta = []
    return song


def _migu_format_size_bytes(meta: dict) -> Optional[int]:
    """咪咕 rateFormats 的 size 字段单位为 MB（可能是数字或 '24.5MB' 字符串）。"""
    raw = meta.get("size") or meta.get("iosSize") or meta.get("androidSize") or meta.get("isize") or meta.get("asize")
    if raw is None:
        return None
    text = str(raw).removesuffix("MB").strip()
    try:
        mb = float(text)
    except Exception:
        return None
    return int(mb * 1024 * 1024) if mb > 0 else None


def migu_item_to_songinfo(item: dict) -> Optional[SongInfo]:
    """咪咕 songResultData.result 条目 → 纯元数据 SongInfo。"""
    content_id = item.get("contentId")
    if not content_id:
        return None
    formats: list[dict] = []
    seen: set[tuple] = set()
    rate_formats = (item.get("newRateFormats") or []) + (item.get("rateFormats") or []) + (item.get("audioFormats") or [])
    for meta in rate_formats:
        if not isinstance(meta, dict):
            continue
        fmt_type = meta.get("formatType")
        if fmt_type not in _MIGU_FORMAT_TIERS or not meta.get("resourceType"):
            continue
        ext, tier = _MIGU_FORMAT_TIERS[fmt_type]
        size = _migu_format_size_bytes(meta)
        key = (ext, tier, size)
        if key in seen:
            continue
        seen.add(key)
        formats.append({"ext": ext, "size_bytes": size, "quality": tier, "label": fmt_type})
    # 高音质在前
    formats.sort(key=lambda f: (TIERS.index(f["quality"]), -(f["size_bytes"] or 0)))
    duration_s = _int_or_none(item.get("duration"))
    cover = safeextractfromdict(item, ["imgItems", -1, "img"], None) or next(
        (item.get(k) for k in ("img3", "img2", "img1") if item.get(k)), None
    )
    if cover and not str(cover).startswith("http"):
        cover = urljoin("https://d.musicapp.migu.cn", str(cover))
    best = formats[0] if formats else {}
    song = SongInfo(
        source=MiguMusicClient.source,
        raw_data={"search": item, "download": {}, "lyric": {}},
        song_name=legalizestring(item.get("name") or item.get("songName") or ""),
        singers=legalizestring(", ".join(
            s.get("name") for s in (item.get("singers") or item.get("singerList") or [])
            if isinstance(s, dict) and s.get("name")
        )),
        album=legalizestring(
            item.get("album")
            or ", ".join(a.get("name") for a in (item.get("albums") or []) if isinstance(a, dict) and a.get("name"))
        ),
        ext=best.get("ext"),
        file_size_bytes=best.get("size_bytes"),
        file_size=SongInfoUtils.byte2mb(best["size_bytes"]) if best.get("size_bytes") else None,
        duration_s=duration_s,
        duration=_hms(duration_s),
        cover_url=cover,
        identifier=str(content_id),
    )
    song.formats_meta = formats
    return song


# ---------------------------------------------------------------- 轻量客户端

class _LightSearchMixin:
    """给 musicdl 源客户端附加「只搜元数据」能力；不复用其 _search/search。

    父类的 ``_constructsearchurls`` 与 session/重试（self.get/self.post）原样复用；
    条目解析委托给上方纯函数，跳过的正是 musicdl 搜索期的逐条下载地址解析。
    """

    _item_parser = None  # type: ignore[assignment]

    def search_light(self, keyword: str) -> list[SongInfo]:
        items: list[SongInfo] = []
        for search_url in self._constructsearchurls(keyword):
            if isinstance(search_url, dict):
                meta = dict(search_url)
                url = meta.pop("url")
                meta.pop("page_no", None)
                meta.pop("page", None)
                meta.pop("params", None)  # sign 仅加密端点需要，本工程不使用
                resp = self.post(url, timeout=_REQUEST_TIMEOUT, **meta)
            else:
                resp = self.get(search_url, timeout=_REQUEST_TIMEOUT)
            for raw_item in self._extract_items(resp):
                song = self._item_parser(raw_item)
                if song is not None:
                    items.append(song)
        # 去重（同一曲目多页/重复出现）
        unique, seen = [], set()
        for song in items:
            if song.identifier in seen:
                continue
            seen.add(song.identifier)
            unique.append(song)
        return unique

    def _extract_items(self, resp) -> list[dict]:
        raise NotImplementedError


class LightQQMusicClient(_LightSearchMixin, QQMusicClient):
    _item_parser = staticmethod(qq_item_to_songinfo)

    def _extract_items(self, resp) -> list[dict]:
        return safeextractfromdict(
            resp2json(resp),
            ["music.search.SearchCgiService.DoSearchForQQMusicMobile", "data", "body", "item_song"],
            [],
        ) or []


class LightNeteaseMusicClient(_LightSearchMixin, NeteaseMusicClient):
    _item_parser = staticmethod(netease_item_to_songinfo)

    def _extract_items(self, resp) -> list[dict]:
        return safeextractfromdict(resp2json(resp), ["result", "songs"], []) or []


class LightMiguMusicClient(_LightSearchMixin, MiguMusicClient):
    _item_parser = staticmethod(migu_item_to_songinfo)

    def _extract_items(self, resp) -> list[dict]:
        return safeextractfromdict(resp2json(resp), ["songResultData", "result"], []) or []


_LIGHT_CLIENTS = {
    "QQMusicClient": LightQQMusicClient,
    "NeteaseMusicClient": LightNeteaseMusicClient,
    "MiguMusicClient": LightMiguMusicClient,
}
# 解析（下载地址）仍用 musicdl 原生客户端
_RESOLVE_CLIENTS = {
    "QQMusicClient": QQMusicClient,
    "NeteaseMusicClient": NeteaseMusicClient,
    "MiguMusicClient": MiguMusicClient,
}


def _new_client(registry: dict, src: str, size: int = DEFAULT_SEARCH_SIZE_PER_SOURCE):
    _WORK_DIR.mkdir(parents=True, exist_ok=True)
    return registry[src](
        search_size_per_source=int(size),
        search_size_per_page=int(size),  # 单页单请求（musicdl 默认每页 10 条会拆成多页）
        auto_set_proxies=False,
        disable_print=True,
        work_dir=str(_WORK_DIR),
    )


# ---------------------------------------------------------------- 档位定向解析（复用 musicdl 协议）

def _probe(client, url: str) -> dict:
    return client.audio_link_tester.test(url=url, renew_session=True)


def _qq_resolve_tier(client: QQMusicClient, search_result: dict, tier: str) -> Optional[SongInfo]:
    mid = search_result.get("mid") or search_result.get("songmid")
    if not mid:
        return None
    for prefix, ext_hint in _QQ_TIER_FILETYPES.get(tier, []):
        try:
            params = {
                "filename": [f"{prefix}{mid}{mid}{ext_hint}"],
                "guid": QQMusicClientUtils.randomguid(),
                "songmid": [mid],
                "songtype": [0],
            }
            payload = QQMusicClientUtils.buildrequestdata(
                params=params,
                module="music.vkey.GetVkey",
                method="UrlGetVkey",
                credential=Credential().fromcookiesdict(client.default_cookies or {}),
                common_override={"ct": "19"},
            )
            resp = client.post(
                QQMusicClientUtils.endpoint,
                data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                timeout=_REQUEST_TIMEOUT,
            )
            body = resp2json(resp)
            purl = safeextractfromdict(
                body, ["music.vkey.GetVkey.UrlGetVkey", "data", "midurlinfo", 0, "purl"], ""
            ) or safeextractfromdict(
                body, ["music.vkey.GetVkey.UrlGetVkey", "data", "midurlinfo", 0, "wifiurl"], ""
            )
            if not purl:
                continue
            url = urljoin(QQMusicClientUtils.music_domain, purl)
            status = _probe(client, url)
            if not (status.get("ok") and status.get("ext") in AudioLinkTester.VALID_AUDIO_EXTS):
                continue
            base = qq_item_to_songinfo(search_result)
            return _resolved_songinfo(base, search_result, status, source=QQMusicClient.source)
        except Exception as exc:
            log.info("QQ 档位解析失败 tier=%s mid=%s err=%s", tier, mid, exc)
    return None


def _netease_resolve_tier(client: NeteaseMusicClient, search_result: dict, tier: str) -> Optional[SongInfo]:
    song_id = search_result.get("id")
    level = _NETEASE_TIER_LEVELS.get(tier)
    if not song_id or not level:
        return None
    try:
        params = {
            "ids": [song_id],
            "level": level,
            "encodeType": "flac",
            "header": json.dumps({"os": "pc", "appver": "", "osver": "", "deviceId": "pyncm!"}),
        }
        enc = EapiCryptoUtils.encryptparams(url=_NETEASE_EAPI_URL, payload=params)
        cookies = {"os": "pc", "appver": "", "osver": "", "deviceId": "pyncm!", **(client.default_cookies or {})}
        resp = client.post(_NETEASE_EAPI_URL, data={"params": enc}, cookies=cookies, timeout=_REQUEST_TIMEOUT)
        url = safeextractfromdict(resp2json(resp), ["data", 0, "url"], "")
        if not (isinstance(url, str) and url.startswith("http")):
            return None
        status = _probe(client, url)
        if not (status.get("ok") and status.get("ext") in AudioLinkTester.VALID_AUDIO_EXTS):
            return None
        base = netease_item_to_songinfo(search_result)
        return _resolved_songinfo(base, search_result, status, source=NeteaseMusicClient.source)
    except Exception as exc:
        log.info("网易档位解析失败 tier=%s id=%s err=%s", tier, song_id, exc)
        return None


def _migu_resolve_tier(client: MiguMusicClient, search_result: dict, tier: str) -> Optional[SongInfo]:
    content_id = search_result.get("contentId")
    copyright_id = search_result.get("copyrightId")
    if not content_id or not copyright_id:
        return None
    rate_formats = (search_result.get("newRateFormats") or []) + (search_result.get("rateFormats") or []) + (search_result.get("audioFormats") or [])
    candidates = [
        m for m in rate_formats
        if isinstance(m, dict) and _MIGU_FORMAT_TIERS.get(m.get("formatType"), (None, None))[1] == tier and m.get("resourceType")
    ]
    candidates.sort(key=_migu_format_size_bytes_or_zero, reverse=True)
    headers = {"Content-Type": "application/json;charset=UTF-8", "birth": "h5page", "signature": "1"}
    for meta in candidates:
        try:
            params = [
                ("contentId", content_id), ("copyrightId", copyright_id),
                ("resourceType", meta["resourceType"]), ("netType", "01"),
                ("toneFlag", meta["formatType"]), ("scene", ""),
                ("lowerQualityContentId", content_id),
            ]
            resp = client.get(_MIGU_LISTEN_URL, params=params, headers=headers, timeout=_REQUEST_TIMEOUT)
            result = client._decryptresp(resp=resp)  # 私有方法：咪咕响应 XOR 解密（契约测试兜底）
            url = safeextractfromdict(result, ["data", "url"], "") or (
                f"https://app.pd.nf.migu.cn/MIGUM3.0/v1.0/content/sub/listenSong.do?channel=mx"
                f"&copyrightId={copyright_id}&contentId={content_id}&toneFlag={meta['formatType']}"
                f"&resourceType={meta['resourceType']}&netType=00"
            )
            url = re.sub(r"(?<=/)MP3_128_16_Stero(?=/)", "MP3_320_16_Stero", str(url))
            if not url.startswith("http"):
                continue
            status = _probe(client, url)
            if not (status.get("ok") and status.get("ext") in AudioLinkTester.VALID_AUDIO_EXTS):
                continue
            base = migu_item_to_songinfo(search_result)
            song = _resolved_songinfo(base, search_result, status, source=MiguMusicClient.source)
            # 咪咕时长以 listen-url 响应为准（搜索条目可能不带 duration）
            listen_duration = _int_or_none(safeextractfromdict(result, ["data", "song", "duration"], 0))
            if song and listen_duration and not song.duration_s:
                song.duration_s, song.duration = listen_duration, _hms(listen_duration)
            return song
        except Exception as exc:
            log.info("咪咕档位解析失败 tier=%s contentId=%s err=%s", tier, content_id, exc)
    return None


def _migu_format_size_bytes_or_zero(meta: dict) -> int:
    return _migu_format_size_bytes(meta) or 0


def _resolved_songinfo(base: Optional[SongInfo], search_result: dict, status: dict, *, source: str) -> Optional[SongInfo]:
    """把探测结果合并进元数据 SongInfo，得到可交给 musicdl download 的对象。"""
    if base is None:
        base = SongInfo(source=source, raw_data={"search": search_result, "download": {}, "lyric": {}})
    base.ext = status.get("ext")
    base.file_size_bytes = status.get("file_size_bytes")
    base.file_size = status.get("file_size")
    base.download_url = status.get("download_url")
    base.download_url_status = dict(status)
    return base if base.with_valid_download_url else None


_TIER_RESOLVERS = {
    "QQMusicClient": _qq_resolve_tier,
    "NeteaseMusicClient": _netease_resolve_tier,
    "MiguMusicClient": _migu_resolve_tier,
}

_LOSSLESS_EXTS = {"flac", "ape", "wav", "dff", "dsf"}


def _honest_quality_label(song: SongInfo) -> str:
    """按探测到的真实格式/码率给标签，而不是请求档位。"""
    ext = (song.ext or "").lower().lstrip(".")
    if ext in _LOSSLESS_EXTS:
        return TIER_LABELS["lossless"]
    bitrate_kbps = 0
    if song.file_size_bytes and song.duration_s:
        bitrate_kbps = int(song.file_size_bytes * 8 / song.duration_s / 1000)
    return TIER_LABELS["high"] if bitrate_kbps >= 256 else TIER_LABELS["standard"]


# ---------------------------------------------------------------- 服务

class LightSearchService:
    """轻量搜索 + 单曲定向解析。无状态（除进程内 TTL 缓存），可并发使用。"""

    def __init__(self, db=None):
        self.db = db

    # ---- 搜索 ----

    def search(
        self,
        keyword: str,
        music_sources: Optional[list[str]] = None,
        size_per_source: int = DEFAULT_SEARCH_SIZE_PER_SOURCE,
    ) -> tuple[list[SongInfo], list[str]]:
        """并发搜索各源并合并结果：单源失败不影响其他源，按来源声明顺序合并。

        每源一次请求，总耗时 ≈ 最慢的源（通常 1s 内）。结果写入 TTL 缓存，
        供 find_item（下载锁定）与翻页/重搜复用。
        """
        keyword = (keyword or "").strip()
        sources = [s for s in (music_sources or DEFAULT_DOWNLOAD_SOURCES) if s in _LIGHT_CLIENTS]
        if not keyword or not sources:
            return [], []
        per_source: dict[str, tuple[list, Optional[str]]] = {}
        futures = {
            executor_submit(self._search_one_source, keyword, src, size_per_source, lane="search"): src
            for src in sources
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                per_source[src] = fut.result()
            except Exception as exc:  # 防御：_search_one_source 已自隔离，这里兜底
                per_source[src] = ([], f"{SOURCE_LABELS.get(src, src)}: {exc}")
        items: list[SongInfo] = []
        errors: list[str] = []
        for src in sources:
            found, error = per_source.get(src, ([], None))
            for song in found:
                song._sonpick_source = src
            items.extend(found)
            if error:
                errors.append(error)
        return items, errors

    def _search_one_source(self, keyword: str, src: str, size: int) -> tuple[list[SongInfo], Optional[str]]:
        cache_key = ("search", keyword.lower(), src, int(size))
        cached = _search_cache.get(cache_key)
        if cached is not None:
            return cached, None
        label = SOURCE_LABELS.get(src, src)
        try:
            client = _new_client(_LIGHT_CLIENTS, src, size)
            items = run_with_hard_timeout(
                lambda: client.search_light(keyword),
                LIGHT_SEARCH_TIMEOUT_SECONDS,
                label=f"{label} 轻量搜索",
            )
        except Exception as exc:
            return [], f"{label}: {exc}"
        # 只缓存非空结果：空列表常是临时波动/限流的信号，缓存会把一次抖动放大成 10 分钟
        if items:
            _search_cache.set(cache_key, items)
        return items, None

    def find_item(self, keyword: str, source: str, song_id: str) -> Optional[SongInfo]:
        """按 song_id 定位搜索结果条目（缓存优先，未命中则重新轻量搜索一次）。"""
        if source not in _LIGHT_CLIENTS or not song_id:
            return None
        items, _ = self.search(keyword, [source])
        for song in items:
            if str(song.identifier) == str(song_id):
                return song
        return None

    # ---- 解析 ----

    def resolve_formats(self, item: SongInfo) -> list[dict]:
        """对锁定单曲并行验证三档格式，返回「已验证可下」列表（高音质在前）。

        供下载确认弹窗使用：先走官方接口（每档 1 请求 + 1 探测）；官方全部
        落空（常见于 VIP/付费曲）时兜底一次第三方解析级联，命中的条目带
        ``via="third_party"`` 标记。第三方也落空才返回空列表（前端仍可直接下载）。

        注意：上游接口可能给不同档位返回同一内容（如咪咕各档回退到同一 mp3、
        网易 lossless/exhigh 落地同一文件）——签名 URL 各不相同，须按
        (格式, 大小) 去重只保留最高档，并按探测到的真实格式/码率生成标签，
        避免「标无损实际 mp3」的假承诺。
        """
        src = getattr(item, "_sonpick_source", None) or item.source
        resolved = self._resolve_all_tiers(item, src)
        formats = []
        seen: set[tuple] = set()
        for tier in TIERS:
            song = resolved.get(tier)
            if song is None:
                continue
            key = (song.ext, song.file_size_bytes) if song.file_size_bytes else ("url", song.download_url)
            if key in seen:
                continue
            seen.add(key)
            formats.append({
                "tier": tier,
                "label": _honest_quality_label(song),
                "ext": song.ext,
                "file_size_bytes": song.file_size_bytes,
                "file_size": song.file_size,
                "via": "official",
            })
        if not formats:
            third = self._resolve_via_third_party(item, src)
            if third is not None:
                # tier=best：worker 收到后按全部档位+第三方重走一遍，语义一致
                formats.append({
                    "tier": "best",
                    "label": _honest_quality_label(third),
                    "ext": third.ext,
                    "file_size_bytes": third.file_size_bytes,
                    "file_size": third.file_size,
                    "via": "third_party",
                })
        return formats

    def resolve_for_download(self, item: SongInfo, tier: str = "best") -> SongInfo:
        """为下载解析单曲：先按目标档位，失败逐档降级，最后第三方解析兜底。"""
        src = getattr(item, "_sonpick_source", None) or item.source
        resolved = self._resolve_all_tiers(item, src)
        order = list(TIERS) if tier in ("best", None, "") else [tier] + [t for t in TIERS if t != tier]
        for t in order:
            song = resolved.get(t)
            if song is not None:
                if t != tier and tier not in ("best", None, ""):
                    log.info("目标档位 %s 不可得，降级到 %s: %s", tier, t, item.song_name)
                return song
        # 官方渠道全部失败 → 第三方解析级联兜底（QQ/网易；咪咕无此机制）
        song = self._resolve_via_third_party(item, src)
        if song is not None:
            return song
        raise RuntimeError(f"{SOURCE_LABELS.get(src, src)}未找到可下载版本")

    def _resolve_all_tiers(self, item: SongInfo, src: str) -> dict[str, Optional[SongInfo]]:
        cache_key = ("resolve", src, str(item.identifier))
        cached = _resolve_cache.get(cache_key)
        if cached is not None:
            return cached
        resolver = _TIER_RESOLVERS.get(src)
        if resolver is None:
            return {}
        search_result = (item.raw_data or {}).get("search") or {}
        result: dict[str, Optional[SongInfo]] = {t: None for t in TIERS}
        futures = {
            executor_submit(self._resolve_one_tier, resolver, src, search_result, tier, lane="search"): tier
            for tier in TIERS
        }
        for fut in as_completed(futures):
            tier = futures[fut]
            try:
                song = fut.result()
                if song is not None:
                    song._sonpick_source = src
                    result[tier] = song
            except Exception as exc:
                log.info("档位解析异常 src=%s tier=%s err=%s", src, tier, exc)
        _resolve_cache.set(cache_key, result)
        return result

    @staticmethod
    def _resolve_one_tier(resolver, src: str, search_result: dict, tier: str) -> Optional[SongInfo]:
        client = _new_client(_RESOLVE_CLIENTS, src)
        return run_with_hard_timeout(
            lambda: resolver(client, search_result, tier),
            LIGHT_SEARCH_TIMEOUT_SECONDS,
            label=f"{SOURCE_LABELS.get(src, src)} {tier} 解析",
        )

    def _resolve_via_third_party(self, item: SongInfo, src: str) -> Optional[SongInfo]:
        if src not in ("QQMusicClient", "NeteaseMusicClient"):
            return None
        # 弹窗验证与 worker 下载会各走一次，缓存避免重复级联（空结果不缓存）
        cache_key = ("resolve3rd", src, str(item.identifier))
        cached = _resolve_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            client = _new_client(_RESOLVE_CLIENTS, src)
            search_result = (item.raw_data or {}).get("search") or {}
            song = run_with_hard_timeout(
                lambda: client._parsewiththirdpartapis(search_result=search_result),  # 私有级联（契约测试兜底）
                THIRD_PARTY_TIMEOUT_SECONDS,
                label=f"{SOURCE_LABELS.get(src, src)} 第三方解析",
            )
        except Exception as exc:
            log.info("第三方解析失败 src=%s err=%s", src, exc)
            return None
        if song is not None and getattr(song, "with_valid_download_url", False):
            song._sonpick_source = src
            if not song.identifier:
                song.identifier = str(item.identifier)
            _resolve_cache.set(cache_key, song)
            return song
        return None


_search_cache = _TTLCache()
_resolve_cache = _TTLCache()
