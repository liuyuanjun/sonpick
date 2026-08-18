"""统一外部 HTTP 客户端：全项目唯一的"取 JSON"入口。

收口 UA / 超时 / 错误处理 / per-host 限流（``host_limiter.get_limiter``），替代各
provider 自带的 ``_http_json`` / 内联 ``urlopen``。musicdl 等无法注入传输层的三方库
不在此列（走 lane 信号量 + 硬超时约束）。

用法：``http_json(url, host="music.163.com", method="POST", data={...}, headers={...})``
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional

from app.services.host_limiter import get_limiter

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def host_from_url(url: str) -> str:
    """从 URL 取 netloc（含端口，小写），作为限流器注册键。"""
    return (urllib.parse.urlparse(str(url)).netloc or "unknown").lower()


def http_json(
    url: str,
    *,
    host: Optional[str] = None,
    method: str = "GET",
    data: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
    max_concurrent: int = 2,
    min_interval: float = 0.3,
    ua: Optional[str] = None,
) -> Any:
    """在 per-host 限流下获取并解析 JSON。

    ``data`` 非空时按 ``application/x-www-form-urlencoded`` 编码为请求体。
    异常不在此吞掉——由调用方决定是返回默认值还是快速失败。
    """
    host_key = host or host_from_url(url)
    hdrs: dict[str, str] = {
        "User-Agent": ua or DEFAULT_UA,
        "Accept": "application/json,text/plain,*/*",
    }
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)

    def _do() -> Any:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8", errors="replace"))

    return get_limiter(host_key, max_concurrent=max_concurrent, min_interval=min_interval).run(_do)
