"""轻量搜索/解析的契约与逻辑测试。

分两类：

1. 元数据映射（纯函数）：用真实抓取的各源搜索响应样例，
   断言 SongInfo 字段（identifier/时长/封面/可得格式/VIP 标记）。
2. musicdl 私有 API 契约：本工程复用了 musicdl 的私有方法
   （精确钉版 + Dependabot 周检），上游升级导致签名漂移时这里直接失败。
"""
import unittest
from unittest import mock

from app.services.light_search_service import (
    LightSearchService,
    kugou_item_to_songinfo,
    kuwo_item_to_songinfo,
    migu_item_to_songinfo,
    netease_item_to_songinfo,
    qianqian_item_to_songinfo,
    qq_item_to_songinfo,
)

# 真实响应样例（2026-09 抓取，已裁剪）
QQ_ITEM = {
    "act": 3,
    "album": {"mid": "000MkMni19ClKG", "title": "叶惠美"},
    "file": {
        "size_128mp3": 4317292,
        "size_320mp3": 0,
        "size_flac": 0,
        "size_hires": 0,
        "size_192ogg": 0,
        "size_96ogg": 2927865,
        "size_48aac": 1642440,
    },
    "interval": 269,
    "mid": "0039MnYb0qxYhV",
    "pay": {"pay_down": 1, "pay_play": 1},
    "singer": [{"name": "周杰伦"}],
    "title": "晴天",
}

NETEASE_ITEM = {
    "id": 347230,
    "name": "晴天",
    "ar": [{"id": 6452, "name": "周杰伦"}],
    "al": {"id": 34209, "name": "叶惠美", "picUrl": "https://p1.music.126.net/abc.jpg"},
    "dt": 269000,
    "privilege": {"fee": 1},
}

MIGU_ITEM = {
    "contentId": "600902000001",
    "copyrightId": "6005669",
    "name": "晴天",
    "singers": [{"name": "周杰伦"}],
    "albums": [{"name": "叶惠美"}],
    "duration": 269,
    "img1": "/prod/img/abc.jpg",
    "newRateFormats": [
        {"formatType": "ZQ24", "resourceType": "2", "size": "62.5MB"},
        {"formatType": "Z3D", "resourceType": "2", "size": "30MB"},  # 加密格式，应跳过
        {"formatType": "HQ", "resourceType": "2", "size": "10.2MB"},
        {"formatType": "PQ", "resourceType": "2", "size": 4.1},
    ],
}

# 酷狗/酷我/千千真实响应样例（2026-09 抓取，已裁剪）
KUGOU_ITEM = {
    "ID": "32100650",
    "SongName": "晴天",
    "SingerName": "周杰伦",
    "AlbumName": "叶惠美",
    "Duration": 269,
    "FileSize": 4317292,
    "ExtName": "mp3",
    "HQFileSize": 10792943,
    "HQExtName": "mp3",
    "SQFileSize": 31633244,
    "SQExtName": "flac",
    "ResFileSize": 55397039,
    "Image": "http://imge.kugou.com/stdmusic/{size}/20230920/abc.jpg",
}

KUWO_ITEM = {
    "MUSICRID": "MUSIC_228908",
    "SONGNAME": "晴天",
    "NAME": "晴天",
    "ARTIST": "周杰伦",
    "ALBUM": "叶惠美",
    "DURATION": "269",
    "web_albumpic_short": "120/s3s94/93/211513640.jpg",
    "MINFO": (
        "level:ff,bitrate:2000,format:flac,size:52.83Mb;"
        "level:p,bitrate:320,format:mp3,size:10.29Mb;"
        "level:h,bitrate:128,format:mp3,size:4.12Mb;"
        "level:s,bitrate:48,format:aac,size:1.57Mb"
    ),
    "N_MINFO": "level:zply,bitrate:20900,format:mflac,size:178.32Mb",  # 加密格式，不收录
}

QIANQIAN_ITEM = {
    "TSID": "T10065400429",
    "id": "T10065400429",
    "title": "晴天",
    "artist": [{"name": "周杰伦"}],
    "albumTitle": "叶惠美",
    "duration": 269,
    "pic": "https://img01.dmhmusic.com/abc.jpg",
    "rateFileInfo": {
        "3000": {"size": 57635329, "format": "flac"},
        "320": {"size": 10759932, "format": "mp3"},
        "128": {"size": 4304124, "format": "mp3"},
        "64": {"size": 2151918, "format": "aac"},
    },
}


class QQMappingTests(unittest.TestCase):
    def test_null_text_normalized(self):
        """musicdl legalizestring 把空字段变成 'NULL'，mapper 出口必须归一为空串。"""
        item = {**QQ_ITEM, "singer": [], "album": {}}
        song = qq_item_to_songinfo(item)
        self.assertEqual(song.singers, "")
        self.assertEqual(song.album, "")

    def test_basic_fields(self):
        song = qq_item_to_songinfo(QQ_ITEM)
        self.assertEqual(song.identifier, "0039MnYb0qxYhV")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.album, "叶惠美")
        self.assertEqual(song.duration_s, 269)
        self.assertEqual(
            song.cover_url,
            "https://y.gtimg.cn/music/photo_new/T002R800x800M000000MkMni19ClKG.jpg",
        )

    def test_formats_skip_zero_sizes_and_order(self):
        song = qq_item_to_songinfo(QQ_ITEM)
        # size_flac/size_320 为 0 → 不可用；只剩 128mp3 与 96ogg（皆为标准档）
        qualities = [f["quality"] for f in song.formats_meta]
        exts = [f["ext"] for f in song.formats_meta]
        self.assertEqual(set(qualities), {"standard"})
        self.assertNotIn("flac", exts)
        # 展示用最佳格式 = 第一个可用格式
        self.assertEqual(song.ext, song.formats_meta[0]["ext"])
        self.assertEqual(song.file_size_bytes, song.formats_meta[0]["size_bytes"])

    def test_lossless_preferred_when_available(self):
        item = dict(QQ_ITEM)
        item["file"] = dict(QQ_ITEM["file"], size_flac=28_000_000, size_320mp3=10_000_000)
        song = qq_item_to_songinfo(item)
        self.assertEqual(song.formats_meta[0]["quality"], "lossless")
        self.assertEqual(song.ext, "flac")
        self.assertEqual(song.file_size_bytes, 28_000_000)

    def test_missing_mid_returns_none(self):
        self.assertIsNone(qq_item_to_songinfo({"title": "x"}))


class NeteaseMappingTests(unittest.TestCase):
    def test_basic_fields(self):
        song = netease_item_to_songinfo(NETEASE_ITEM)
        self.assertEqual(song.identifier, "347230")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.album, "叶惠美")
        self.assertEqual(song.duration_s, 269)
        self.assertEqual(song.cover_url, "https://p1.music.126.net/abc.jpg")
        self.assertEqual(song.formats_meta, [])


class MiguMappingTests(unittest.TestCase):
    def test_basic_fields(self):
        song = migu_item_to_songinfo(MIGU_ITEM)
        self.assertEqual(song.identifier, "600902000001")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.album, "叶惠美")
        self.assertEqual(song.duration_s, 269)
        # 相对封面路径应补全域名
        self.assertEqual(song.cover_url, "https://d.musicapp.migu.cn/prod/img/abc.jpg")

    def test_formats_skip_encrypted_and_convert_mb(self):
        song = migu_item_to_songinfo(MIGU_ITEM)
        labels = [f["label"] for f in song.formats_meta]
        self.assertNotIn("Z3D", labels)  # 加密格式跳过
        self.assertEqual(labels, ["ZQ24", "HQ", "PQ"])  # 高音质在前
        zq24 = song.formats_meta[0]
        self.assertEqual(zq24["quality"], "lossless")
        self.assertEqual(zq24["size_bytes"], int(62.5 * 1024 * 1024))
        # 数字型 size（MB）也要能解析
        pq = song.formats_meta[-1]
        self.assertEqual(pq["size_bytes"], int(4.1 * 1024 * 1024))


class KugouMappingTests(unittest.TestCase):
    def test_basic_fields(self):
        song = kugou_item_to_songinfo(KUGOU_ITEM)
        self.assertEqual(song.identifier, "32100650")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.album, "叶惠美")
        self.assertEqual(song.duration_s, 269)
        # 封面 {size} 占位符替换
        self.assertNotIn("{size}", song.cover_url)

    def test_formats_order_and_best(self):
        song = kugou_item_to_songinfo(KUGOU_ITEM)
        self.assertEqual(
            [(f["label"], f["quality"]) for f in song.formats_meta],
            [("Hi-Res", "lossless"), ("FLAC", "lossless"), ("MP3 320", "high"), ("MP3", "standard")],
        )
        self.assertEqual(song.ext, "flac")  # best = Hi-Res（flac）
        self.assertEqual(song.file_size_bytes, 55397039)

    def test_missing_id_returns_none(self):
        self.assertIsNone(kugou_item_to_songinfo({"SongName": "x"}))


class KuwoMappingTests(unittest.TestCase):
    def test_basic_fields(self):
        song = kuwo_item_to_songinfo(KUWO_ITEM)
        self.assertEqual(song.identifier, "MUSIC_228908")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.duration_s, 269)
        # 封面尺寸段 120 → 500
        self.assertEqual(song.cover_url, "https://img1.kuwo.cn/star/albumcover/500/s3s94/93/211513640.jpg")

    def test_minfo_parsed_and_encrypted_excluded(self):
        song = kuwo_item_to_songinfo(KUWO_ITEM)
        labels = [f["label"] for f in song.formats_meta]
        self.assertEqual(labels, ["FLAC 2000k", "MP3 320k", "MP3 128k", "AAC 48k"])
        self.assertNotIn("MFLAC", " ".join(labels))  # N_MINFO 加密格式不收录
        self.assertEqual(song.formats_meta[0]["quality"], "lossless")
        self.assertEqual(song.formats_meta[0]["size_bytes"], int(52.83 * 1024 * 1024))
        self.assertEqual(song.ext, "flac")

    def test_missing_rid_returns_none(self):
        self.assertIsNone(kuwo_item_to_songinfo({"NAME": "x"}))


class QianqianMappingTests(unittest.TestCase):
    def test_basic_fields(self):
        song = qianqian_item_to_songinfo(QIANQIAN_ITEM)
        self.assertEqual(song.identifier, "T10065400429")
        self.assertEqual(song.song_name, "晴天")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.duration_s, 269)
        self.assertEqual(song.cover_url, "https://img01.dmhmusic.com/abc.jpg")

    def test_rate_file_info_sorted_by_tier(self):
        song = qianqian_item_to_songinfo(QIANQIAN_ITEM)
        self.assertEqual(
            [(f["label"], f["quality"]) for f in song.formats_meta],
            [("FLAC", "lossless"), ("MP3 320k", "high"), ("MP3 128k", "standard"), ("AAC 64k", "standard")],
        )
        self.assertEqual(song.ext, "flac")
        self.assertEqual(song.file_size_bytes, 57635329)


class ResolveFlowTests(unittest.TestCase):
    def _item(self):
        song = qq_item_to_songinfo(QQ_ITEM)
        song._sonpick_source = "QQMusicClient"
        return song

    def test_resolve_for_download_prefers_requested_tier(self):
        svc = LightSearchService(None)
        item = self._item()
        high = mock.Mock(identifier=item.identifier)
        resolved = {"lossless": None, "high": high, "standard": mock.Mock()}
        with mock.patch.object(svc, "_resolve_all_tiers", return_value=resolved):
            out = svc.resolve_for_download(item, "high")
        self.assertIs(out, high)

    def test_resolve_for_download_falls_down_then_third_party(self):
        svc = LightSearchService(None)
        item = self._item()
        standard = mock.Mock(identifier=item.identifier)
        resolved = {"lossless": None, "high": None, "standard": standard}
        with mock.patch.object(svc, "_resolve_all_tiers", return_value=resolved):
            out = svc.resolve_for_download(item, "lossless")
        self.assertIs(out, standard)

        with (
            mock.patch.object(svc, "_resolve_all_tiers", return_value={"lossless": None, "high": None, "standard": None}),
            mock.patch.object(svc, "_resolve_via_third_party", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                svc.resolve_for_download(item, "best")

    def test_find_item_matches_identifier_as_string(self):
        svc = LightSearchService(None)
        item = self._item()
        with mock.patch.object(svc, "search", return_value=([item], [])):
            self.assertIs(svc.find_item("kw", "QQMusicClient", "0039MnYb0qxYhV"), item)
            self.assertIsNone(svc.find_item("kw", "QQMusicClient", "other"))

    def test_resolve_formats_only_lists_verified(self):
        svc = LightSearchService(None)
        item = self._item()
        high = mock.Mock(ext=".mp3", file_size_bytes=10_000_000, file_size="9.54 MB", duration_s=269)
        with mock.patch.object(
            svc, "_resolve_all_tiers", return_value={"lossless": None, "high": high, "standard": None}
        ):
            formats = svc.resolve_formats(item)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0]["tier"], "high")
        self.assertEqual(formats[0]["ext"], ".mp3")
        # 标签按真实格式/码率：mp3 10MB@269s ≈ 297kbps → 高品质
        self.assertEqual(formats[0]["label"], "高品质")

    def test_resolve_formats_dedupes_same_content(self):
        # 上游给不同档位返回同一内容（同 ext+大小）时只保留最高档
        svc = LightSearchService(None)
        item = self._item()
        same = mock.Mock(ext=".mp3", file_size_bytes=10_000_000, file_size="9.54 MB", duration_s=269)
        with mock.patch.object(
            svc,
            "_resolve_all_tiers",
            return_value={"lossless": same, "high": same, "standard": same},
        ):
            formats = svc.resolve_formats(item)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0]["tier"], "lossless")

    def test_resolve_formats_falls_back_to_third_party(self):
        # 官方三档全空（VIP/付费曲常见）→ 弹窗也要给出第三方解析的可下格式
        svc = LightSearchService(None)
        item = self._item()
        third = mock.Mock(ext=".flac", file_size_bytes=30_000_000, file_size="28.61 MB", duration_s=269)
        with (
            mock.patch.object(svc, "_resolve_all_tiers", return_value={"lossless": None, "high": None, "standard": None}),
            mock.patch.object(svc, "_resolve_via_third_party", return_value=third) as third_mock,
        ):
            formats = svc.resolve_formats(item)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0]["tier"], "best")  # worker 收到 best 会全档位+第三方重走，语义一致
        self.assertEqual(formats[0]["via"], "third_party")
        self.assertEqual(formats[0]["label"], "无损")

    def test_resolve_formats_skips_third_party_when_official_available(self):
        # 官方有可下格式时不做第三方级联（省一次慢调用）
        svc = LightSearchService(None)
        item = self._item()
        high = mock.Mock(ext=".mp3", file_size_bytes=10_000_000, file_size="9.54 MB", duration_s=269)
        with (
            mock.patch.object(svc, "_resolve_all_tiers", return_value={"lossless": None, "high": high, "standard": None}),
            mock.patch.object(svc, "_resolve_via_third_party") as third_mock,
        ):
            formats = svc.resolve_formats(item)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0]["via"], "official")
        third_mock.assert_not_called()


class MusicdlPrivateApiContractTests(unittest.TestCase):
    """本工程复用的 musicdl 私有方法/工具在上游升级后仍需存在且签名兼容。"""

    def test_private_surface_exists(self):
        from musicdl.modules.sources import (
            KugouMusicClient,
            KuwoMusicClient,
            MiguMusicClient,
            NeteaseMusicClient,
            QianqianMusicClient,
            QQMusicClient,
        )
        from musicdl.modules.utils import AudioLinkTester, SongInfo, SongInfoUtils
        from musicdl.modules.utils.neteaseutils import EapiCryptoUtils
        from musicdl.modules.utils.qqutils import Credential, QQMusicClientUtils

        for cls in (QQMusicClient, NeteaseMusicClient, MiguMusicClient, KugouMusicClient, KuwoMusicClient, QianqianMusicClient):
            self.assertTrue(hasattr(cls, "_constructsearchurls"), cls.__name__)
            self.assertTrue(hasattr(cls, "_parsewithofficialapiv1"), cls.__name__)
        for cls in (QQMusicClient, NeteaseMusicClient, KugouMusicClient, KuwoMusicClient):
            self.assertTrue(hasattr(cls, "_parsewiththirdpartapis"), cls.__name__)
        self.assertTrue(hasattr(MiguMusicClient, "_decryptresp"))
        self.assertTrue(hasattr(AudioLinkTester, "test"))
        self.assertTrue(hasattr(AudioLinkTester, "VALID_AUDIO_EXTS"))
        self.assertTrue(hasattr(QQMusicClientUtils, "buildrequestdata"))
        self.assertTrue(hasattr(QQMusicClientUtils, "randomguid"))
        self.assertTrue(hasattr(Credential, "fromcookiesdict"))
        self.assertTrue(hasattr(EapiCryptoUtils, "encryptparams"))
        self.assertTrue(hasattr(SongInfoUtils, "seconds2hms"))
        self.assertTrue(hasattr(SongInfoUtils, "byte2mb"))
        self.assertTrue(hasattr(SongInfo, "with_valid_download_url"))

    def test_light_clients_construct_and_expose_search_light(self):
        from app.services.light_search_service import _LIGHT_CLIENTS

        for src, cls in _LIGHT_CLIENTS.items():
            client = cls(
                search_size_per_source=5,
                auto_set_proxies=False,
                disable_print=True,
                work_dir="/tmp/musicdl_light_test",
            )
            self.assertTrue(hasattr(client, "search_light"), src)
            # _constructsearchurls 不依赖网络（仅构造请求），可直接调用
            urls = client._constructsearchurls("晴天")
            self.assertTrue(urls, src)


if __name__ == "__main__":
    unittest.main()
