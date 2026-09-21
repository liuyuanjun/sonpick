"""歌单导入（playlist_import_service）测试。

- URL 平台识别与歌单 ID 提取（覆盖六源常见链接形式，含 fragment query 与短链兜底前形态）
- 酷狗/酷我歌单形状适配器（与搜索形状不同的两源）
- musicdl 私有面契约：HOSTS 常量、千千签名方法、parseplaylist 存在性
  （上游升级后若这些面变化，这里会失败，提醒同步 playlist_import_service）
"""
import unittest

from app.services.playlist_import_service import (
    _kugou_playlist_item_to_songinfo,
    _kuwo_playlist_item_to_songinfo,
    detect_playlist_source,
    _extract_playlist_id,
)


class DetectSourceTests(unittest.TestCase):
    def test_six_platforms(self):
        cases = {
            "https://y.qq.com/n/ryqq/playlist/7729596131": "QQMusicClient",
            "https://music.163.com/#/playlist?id=3039971654": "NeteaseMusicClient",
            "https://m.music.163.com/playlist?id=1": "NeteaseMusicClient",
            "https://music.migu.cn/v3/music/playlist/233754996": "MiguMusicClient",
            "https://www.kugou.com/yy/special/single/6409645.html": "KugouMusicClient",
            "https://www.kuwo.cn/playlist_detail/2867496601": "KuwoMusicClient",
            "https://m.kuwo.cn/newh5app/playlist/2867496601": "KuwoMusicClient",
            "https://music.91q.com/songlist/309719": "QianqianMusicClient",
            "https://music.taihe.com/songlist/123": "QianqianMusicClient",
            "https://music.baidu.com/songlist/123": "QianqianMusicClient",
        }
        for url, src in cases.items():
            self.assertEqual(detect_playlist_source(url), src, url)

    def test_unknown_host(self):
        self.assertIsNone(detect_playlist_source("https://open.spotify.com/playlist/abc"))
        self.assertIsNone(detect_playlist_source("not-a-url"))


class ExtractIdTests(unittest.TestCase):
    def test_fragment_query(self):
        self.assertEqual(
            _extract_playlist_id("https://music.163.com/#/playlist?id=3039971654", "NeteaseMusicClient"),
            "3039971654",
        )

    def test_query_id(self):
        self.assertEqual(
            _extract_playlist_id("https://y.qq.com/n/ryqq/playlist/12345", "QQMusicClient"),
            "12345",
        )
        self.assertEqual(
            _extract_playlist_id("https://music.163.com/playlist?id=99", "NeteaseMusicClient"),
            "99",
        )

    def test_path_tail_with_suffix(self):
        self.assertEqual(
            _extract_playlist_id("https://www.kugou.com/yy/special/single/6409645.html", "KugouMusicClient"),
            "6409645",
        )

    def test_empty_path(self):
        self.assertIsNone(_extract_playlist_id("https://music.91q.com/", "QianqianMusicClient"))


class KugouAdapterTests(unittest.TestCase):
    ITEM = {
        "hash": "DBC0207490EB51153EF933EF5A7E98E4",
        "name": "周杰伦 - 以父之名",
        "albuminfo": {"name": "叶惠美"},
        "timelen": 342000,
        "cover": "http://img/{size}/x.jpg",
    }

    def test_split_and_convert(self):
        song = _kugou_playlist_item_to_songinfo(self.ITEM)
        self.assertEqual(song.song_name, "以父之名")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.album, "叶惠美")
        self.assertEqual(song.duration_s, 342)
        self.assertEqual(song.identifier, self.ITEM["hash"])
        self.assertNotIn("{size}", song.cover_url)
        # 下载解析依赖 raw_data.search 原始字典（musicdl 官方/第三方解析都吃这个形状）
        self.assertIs(song.raw_data["search"], self.ITEM)

    def test_no_dash_in_name(self):
        song = _kugou_playlist_item_to_songinfo({**self.ITEM, "name": "晴天"})
        self.assertEqual(song.song_name, "晴天")
        # 无歌手字段时为空串：mapper 出口统一经 _legalize 归一，不再漏出 musicdl 的 'NULL'
        self.assertEqual(song.singers, "")

    def test_missing_hash_returns_none(self):
        self.assertIsNone(_kugou_playlist_item_to_songinfo({"name": "x"}))


class KuwoAdapterTests(unittest.TestCase):
    ITEM = {
        "musicrid": "MUSIC_226543302",
        "name": "最伟大的作品",
        "artist": "周杰伦",
        "album": "最伟大的作品",
        "duration": 244,
        "pic": "https://img1.kuwo.cn/x.jpg",
    }

    def test_lowercase_keys(self):
        song = _kuwo_playlist_item_to_songinfo(self.ITEM)
        self.assertEqual(song.song_name, "最伟大的作品")
        self.assertEqual(song.singers, "周杰伦")
        self.assertEqual(song.duration_s, 244)
        self.assertEqual(song.identifier, "MUSIC_226543302")
        self.assertIs(song.raw_data["search"], self.ITEM)

    def test_missing_rid_returns_none(self):
        self.assertIsNone(_kuwo_playlist_item_to_songinfo({"name": "x"}))


class MusicdlContractTests(unittest.TestCase):
    """钉版依赖的私有面：上游升级若改动，本测试先红。"""

    def test_hosts_constants(self):
        from musicdl.modules.sources.kugou import KUGOU_MUSIC_HOSTS
        from musicdl.modules.sources.kuwo import KUWO_MUSIC_HOSTS
        from musicdl.modules.sources.migu import MIGU_MUSIC_HOSTS
        from musicdl.modules.sources.netease import NETEASE_MUSIC_HOSTS
        from musicdl.modules.sources.qianqian import QIANQIAN_MUSIC_HOSTS
        from musicdl.modules.sources.qq import QQ_MUSIC_HOSTS

        self.assertIn("y.qq.com", QQ_MUSIC_HOSTS)
        self.assertIn("music.163.com", NETEASE_MUSIC_HOSTS)
        self.assertIn("music.migu.cn", MIGU_MUSIC_HOSTS)
        self.assertIn("www.kugou.com", KUGOU_MUSIC_HOSTS)
        self.assertIn("www.kuwo.cn", KUWO_MUSIC_HOSTS)
        self.assertIn("music.91q.com", QIANQIAN_MUSIC_HOSTS)

    def test_qianqian_sign_method(self):
        from musicdl.modules.sources import QianqianMusicClient

        self.assertTrue(hasattr(QianqianMusicClient, "_addsignandtstoparams"))
        self.assertTrue(hasattr(QianqianMusicClient, "APPID"))

    def test_parseplaylist_still_exists(self):
        # 我们的提取规则对齐 parseplaylist；它被删/改名时提醒重新核对
        from musicdl.modules.sources import (
            KugouMusicClient,
            KuwoMusicClient,
            MiguMusicClient,
            NeteaseMusicClient,
            QianqianMusicClient,
            QQMusicClient,
        )

        for cls in (QQMusicClient, NeteaseMusicClient, MiguMusicClient, KugouMusicClient, KuwoMusicClient, QianqianMusicClient):
            self.assertTrue(hasattr(cls, "parseplaylist"), cls.__name__)


if __name__ == "__main__":
    unittest.main()
