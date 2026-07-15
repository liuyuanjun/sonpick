"""LRC lyrics parsing helpers."""
from __future__ import annotations

import re
from pathlib import Path

from app.services.library_layout import find_lrc_sidecar
from typing import Optional

_LRC_LINE = re.compile(
    r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\](.*)"
)

# Prefer timed LRC; plain txt only as last resort for same-stem sidecar.
SIDE_LRC_EXTS = (".lrc", ".LRC", ".txt", ".TXT")


def parse_lrc_text(raw: str) -> list[dict]:
    """Parse LRC text into [{time, text}, ...] sorted by time."""
    lines: list[dict] = []
    for line in (raw or "").splitlines():
        matches = list(_LRC_LINE.finditer(line.strip()))
        if not matches:
            continue
        for m in matches:
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            frac = m.group(3) or "0"
            # Support .xx / .xxx
            if len(frac) == 1:
                frac_sec = int(frac) / 10
            elif len(frac) == 2:
                frac_sec = int(frac) / 100
            else:
                frac_sec = int(frac[:3]) / 1000
            text = m.group(4).strip()
            if not text:
                continue
            t = minutes * 60 + seconds + frac_sec
            lines.append({"time": round(t, 3), "text": text})
    lines.sort(key=lambda x: x["time"])
    return lines


def plain_text_to_lines(raw: str) -> list[dict]:
    """Convert untimed lyric text into display lines (time=0)."""
    out: list[dict] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s:
            continue
        # skip pure metadata tags like [ar:xx]
        if s.startswith("[") and s.endswith("]") and ":" in s and not _LRC_LINE.match(s):
            continue
        out.append({"time": 0.0, "text": s})
    return out


def looks_like_remote_path(path: str | None) -> bool:
    """Heuristic: if path is relative and doesn't exist locally, treat as remote."""
    if not path:
        return False
    p = Path(path)
    if p.is_absolute() and p.exists():
        return False
    return not p.exists()


def fetch_remote_lrc_text(lrc_path: str, db) -> str | None:
    """Download LRC content from WebDAV. Returns raw text or None."""
    try:
        from app.services.webdav_service import WebDAVService
        svc = WebDAVService(db)
        data = svc.download_bytes(lrc_path, max_bytes=512 * 1024)
        text = data.decode("utf-8", errors="ignore")
        return text if text.strip() else None
    except Exception:
        return None


def _read_local_text(path: Path) -> Optional[str]:
    try:
        if path.exists() and path.is_file():
            raw = path.read_text(encoding="utf-8", errors="ignore")
            return raw if raw.strip() else None
    except Exception:
        return None
    return None


def _load_raw_from_path(lrc_path: Optional[str], db=None) -> Optional[str]:
    if not lrc_path:
        return None

    path = Path(lrc_path)
    raw = _read_local_text(path)
    if raw:
        return raw

    if db is None:
        return None

    # Remote WebDAV path — download content
    if not path.is_absolute():
        return fetch_remote_lrc_text(lrc_path, db)

    # Absolute path that doesn't exist — try as remote relative
    rel = str(lrc_path).replace("\\", "/").lstrip("/")
    if rel:
        return fetch_remote_lrc_text(rel, db)
    return None


def load_lyrics(lrc_path: Optional[str], db=None) -> tuple[list[dict], Optional[str]]:
    """Load and parse an LRC file. Supports both local paths and WebDAV remote paths.

    When db is provided and the path is not a local file, it will attempt to
    download the LRC content via WebDAV.
    Untimed plain-text lyrics fall back to display-only lines.
    """
    raw = _load_raw_from_path(lrc_path, db=db)
    if not raw or not raw.strip():
        return [], None
    lines = parse_lrc_text(raw)
    if not lines:
        lines = plain_text_to_lines(raw)
    return lines, raw


def _as_path_str(path: str | Path) -> str:
    return str(path)


def candidate_lrc_paths(song) -> list[str]:
    """Derive same-stem LRC candidates from song audio paths.

    Order: existing lrc_path first, then local sidecars, then remote sidecars.
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(p: Optional[str]):
        if not p:
            return
        key = str(p).replace("\\", "/")
        if key in seen:
            return
        seen.add(key)
        out.append(str(p))

    add(getattr(song, "lrc_path", None))

    local = getattr(song, "local_path", None)
    if local:
        audio = Path(local)
        # layout helper first
        try:
            found = find_lrc_sidecar(audio)
            if found:
                add(str(found))
        except Exception:
            pass
        # same stem next to audio: foo.flac -> foo.lrc / foo.txt
        for ext in SIDE_LRC_EXTS:
            add(str(audio.with_suffix(ext)))
            add(str(audio.with_suffix("")) + ext)
        # case-insensitive / partial stem match in the same folder
        try:
            stem_low = audio.stem.lower()
            parent = audio.parent
            if parent.is_dir():
                fuzzy: list[Path] = []
                for child in parent.iterdir():
                    if not child.is_file():
                        continue
                    low = child.name.lower()
                    if not low.endswith((".lrc", ".txt")):
                        continue
                    cstem = child.stem.lower()
                    if cstem == stem_low or stem_low in cstem or cstem in stem_low:
                        fuzzy.append(child)
                fuzzy.sort(key=lambda c: (0 if c.suffix.lower() == ".lrc" else 1, abs(len(c.stem) - len(audio.stem)), c.name))
                for c in fuzzy[:6]:
                    add(str(c))
        except Exception:
            pass

    remote = getattr(song, "webdav_path", None)
    if remote:
        remote_norm = str(remote).replace("\\", "/").lstrip("/")
        # strip audio extension if present
        if "." in remote_norm.rsplit("/", 1)[-1]:
            stem_remote = remote_norm.rsplit(".", 1)[0]
        else:
            stem_remote = remote_norm
        for ext in (".lrc", ".LRC", ".txt", ".TXT"):
            add(stem_remote + ext)

    return out


def resolve_lrc_path(song, db=None) -> Optional[str]:
    """Return first readable LRC path for song (local or remote)."""
    for cand in candidate_lrc_paths(song):
        if _load_raw_from_path(cand, db=db):
            return cand
    return None


def load_lyrics_for_song(song, db=None, *, persist: bool = True) -> tuple[list[dict], Optional[str], Optional[str]]:
    """Load lyrics for a Song row, with same-stem sidecar fallback.

    Returns (lines, raw, resolved_path).
    When persist=True and a better path is found, write song.lrc_path and commit if needed.
    """
    # 1) Prefer stored path if still valid
    stored = getattr(song, "lrc_path", None)
    lines, raw = load_lyrics(stored, db=db)
    if raw:
        return lines, raw, stored

    # 2) Discover same-stem sidecars
    resolved = None
    raw = None
    for cand in candidate_lrc_paths(song):
        if cand == stored:
            continue
        trial_lines, trial_raw = load_lyrics(cand, db=db)
        if trial_raw:
            resolved = cand
            lines, raw = trial_lines, trial_raw
            break

    if not raw:
        # 2b) embedded lyrics in local audio → materialize .lrc sidecar
        local = getattr(song, "local_path", None)
        if local and Path(local).is_file():
            try:
                from app.services.media_meta_service import read_audio_tags
                tags = read_audio_tags(local)
                emb = tags.get("lyrics") if tags else None
                if emb and str(emb).strip():
                    target = Path(local).with_suffix(".lrc")
                    body = str(emb).replace("\r\n", "\n").strip()
                    if not target.exists():
                        target.write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")
                    trial_lines, trial_raw = load_lyrics(str(target), db=None)
                    if trial_raw:
                        resolved, lines, raw = str(target), trial_lines, trial_raw
            except Exception:
                pass

    if not raw:
        return [], None, None

    # 3) Backfill DB path so later requests hit directly
    if persist and resolved and getattr(song, "lrc_path", None) != resolved:
        try:
            song.lrc_path = resolved
            if db is not None:
                db.add(song)
                db.commit()
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass

    return lines, raw, resolved
