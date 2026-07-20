"""Chromaprint/AcoustID provider with graceful dependency fallback."""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from app.services.scrape.base import ScrapeQuery, ScrapeResult

NAME = "acoustid"


def fingerprint_status(api_key: str | None) -> dict:
    binary = shutil.which("fpcalc")
    if not binary:
        return {"available": False, "message": "未检测到 fpcalc；请在运行环境安装 chromaprint"}
    if not api_key:
        return {"available": False, "message": "未配置 AcoustID API Key；请在刮削源页面保存后启用"}
    return {"available": True, "message": "Chromaprint 与 AcoustID 已就绪"}


def _fingerprint(path: str, *, timeout: float) -> tuple[str, int] | None:
    binary = shutil.which("fpcalc")
    if not binary or not Path(path).is_file():
        return None
    try:
        result = subprocess.run([binary, "-json", path], capture_output=True, text=True, timeout=max(5, int(timeout)))
        payload = json.loads(result.stdout or "{}")
        fingerprint = str(payload.get("fingerprint") or "")
        duration = int(payload.get("duration") or 0)
        return (fingerprint, duration) if fingerprint and duration else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def lookup_acoustid(path: str, api_key: str, *, timeout: float = 15.0) -> Optional[ScrapeResult]:
    result = _fingerprint(path, timeout=timeout)
    if not result or not api_key:
        return None
    fingerprint, duration = result
    params = urllib.parse.urlencode({
        "client": api_key, "meta": "recordings+releasegroups+releases+artists", "duration": duration, "fingerprint": fingerprint,
    })
    request = urllib.request.Request(
        f"https://api.acoustid.org/v2/lookup?{params}",
        headers={"Accept": "application/json", "User-Agent": "Sonpick/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    for item in payload.get("results") or []:
        for recording in item.get("recordings") or []:
            artists = ", ".join(artist.get("name", "") for artist in recording.get("artists") or [] if artist.get("name"))
            releases = recording.get("releases") or []
            release = releases[0] if releases else {}
            return ScrapeResult(
                title=recording.get("title"), artist=artists or None, album=release.get("title"),
                duration=duration, provider=NAME, score=float(item.get("score") or 0) * 100,
                raw={"recording_id": recording.get("id"), "release_id": release.get("id")},
            )
    return None
