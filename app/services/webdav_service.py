from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

import aiohttp
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from webdav3.client import Client

from app.models import AppSettings, MediaSource, Song, SongFile
from app.routers.settings import _ensure_settings
from app.schemas import decrypt_text
from app.services.operation_log_service import write_log
from app.services.song_file_resolver import NoPlayableSongFileError, SongFileResolver


ProgressCb = Optional[Callable[[str], None]]


class WebDAVService:
    def __init__(self, db: Session | None = None, source: MediaSource | None = None, source_id: int | None = None):
        self.db = db
        self._source = source
        self._source_id = source_id

    def _get_source(self) -> MediaSource | None:
        if self._source is not None:
            return self._source
        if self._source_id is not None and self.db:
            return self.db.get(MediaSource, self._source_id)
        return None

    def _get_config(self) -> AppSettings:
        if self.db:
            return _ensure_settings(self.db)
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            return _ensure_settings(db)
        finally:
            db.close()

    def _require_url(self, cfg: AppSettings | None = None) -> str:
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            return source.webdav_url.strip()
        cfg = cfg or self._get_config()
        url = (cfg.webdav_url or "").strip()
        if not url:
            raise ValueError("WebDAV 未配置")
        return url

    def _client(self, root_url: str | None = None) -> Client:
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            password = decrypt_text(source.webdav_password_enc) or ""
            if root_url:
                hostname = str(root_url).rstrip("/") + "/"
            else:
                hostname = source.webdav_url.strip().rstrip("/") + "/"
            return Client({
                "webdav_hostname": hostname,
                "webdav_login": source.webdav_username or "",
                "webdav_password": password,
            })
        cfg = self._get_config()
        password = decrypt_text(cfg.webdav_password_enc) or ""
        if root_url:
            hostname = str(root_url).rstrip("/") + "/"
        else:
            hostname = self._require_url(cfg).rstrip("/") + "/"
        return Client({
            "webdav_hostname": hostname,
            "webdav_login": cfg.webdav_username or "",
            "webdav_password": password,
        })

    @staticmethod
    def _split_root_and_path(webdav_url: str | None) -> tuple[str, str]:
        """把用户配置的 URL 拆成服务器根地址 + 起始目录。"""
        url = (webdav_url or "").strip().rstrip("/")
        if not url:
            raise ValueError("WebDAV 未配置")
        parts = url.split("/")
        if len(parts) >= 4 and parts[2]:
            root = parts[0] + "//" + parts[2] + "/"
            rel = "/".join(parts[3:])
            return root, rel
        return url + "/", ""

    @staticmethod
    def _norm_rel(path: str | None) -> str:
        return (path or "").strip().strip("/")

    def _remote_base_dir(self, cfg: AppSettings | None = None) -> str:
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            _, base_dir = self._split_root_and_path(source.webdav_url)
            extra = self._norm_rel(source.remote_dir)
            parts = [p for p in [self._norm_rel(base_dir), extra] if p]
            return "/".join(parts)
        cfg = cfg or self._get_config()
        _, base_dir = self._split_root_and_path(cfg.webdav_url)
        extra = self._norm_rel(getattr(cfg, "webdav_remote_dir", None))
        parts = [p for p in [self._norm_rel(base_dir), extra] if p]
        return "/".join(parts)

    def _join_remote(self, *parts: str) -> str:
        cleaned = [self._norm_rel(p) for p in parts if self._norm_rel(p)]
        return "/".join(cleaned)

    def list(self, path: str | None = "") -> list[dict]:
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, base_dir = self._split_root_and_path(source.webdav_url)
            client = self._client(root_url=root_url)
        else:
            cfg = self._get_config()
            root_url, base_dir = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)
        client.check = lambda p: True

        rel = self._norm_rel(path)
        if base_dir and rel:
            target = f"{base_dir}/{rel}"
        elif base_dir:
            target = base_dir
        else:
            target = rel

        try:
            items = client.list(target or "/")
        except Exception:
            items = client.list((target or "") + "/")

        if not items:
            return []

        result = []
        for name in items:
            if name is None:
                continue
            name = str(name)
            if name in (".", "..", ""):
                continue
            clean = name.rstrip("/")
            if not clean:
                continue
            is_dir = name.endswith("/")
            full = f"{rel}/{clean}".lstrip("/") if rel else clean
            result.append({
                "name": clean.split("/")[-1],
                "path": full,
                "is_dir": is_dir,
                "size": None,
            })
        return result

    def delete(self, path: str | None) -> dict:
        """删除远程文件或目录（path 相对曲库远程根目录，与 list 返回的 path 一致）。"""
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, base_dir = self._split_root_and_path(source.webdav_url)
        else:
            cfg = self._get_config()
            root_url, base_dir = self._split_root_and_path(cfg.webdav_url)
        client = self._client(root_url=root_url)

        rel = self._norm_rel(path)
        if not rel:
            raise ValueError("不允许删除远程根目录")
        target = f"{base_dir}/{rel}" if base_dir else rel
        client.clean(target)

        # 清理关联的曲库记录
        removed_records = 0
        if self.db:
            from app.models import SongFile
            song_files = (
                self.db.query(SongFile)
                .filter((SongFile.webdav_path == rel) | (SongFile.webdav_path.like(rel + "/%")))
                .all()
            )
            song_ids = {sf.song_id for sf in song_files if sf.song_id}
            for sf in song_files:
                self.db.delete(sf)
            removed_records = len(song_files)
            if song_ids:
                for song in self.db.query(Song).filter(Song.id.in_(song_ids)).all():
                    remaining = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
                    has_local = any(sf.local_path for sf in remaining)
                    has_remote = any(sf.webdav_path for sf in remaining)
                    song.status = "both" if has_local and has_remote else "local" if has_local else "remote"

            write_log(
                self.db,
                action="delete",
                target="file",
                status="success",
                title=rel.split("/")[-1],
                message=f"删除 WebDAV 项目: {rel}",
                remote_path=rel,
                detail={"path": rel, "removed_records": removed_records},
                commit=False,
            )
            self.db.commit()
        return {"ok": True, "removed_records": removed_records}

    def list_recursive(
        self,
        path: str | None = "",
        *,
        max_depth: int = 12,
        max_items: int = 20000,
    ) -> list[dict]:
        """深度优先递归列出文件；目录项不会返回，仅返回文件。"""
        out: list[dict] = []
        stack: list[tuple[str, int]] = [(self._norm_rel(path), 0)]
        seen_dirs: set[str] = set()

        while stack:
            current, depth = stack.pop()
            key = current or ""
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            try:
                items = self.list(current)
            except Exception:
                continue
            for item in items:
                full = self._norm_rel(item.get("path") or item.get("name") or "")
                if not full:
                    continue
                if item.get("is_dir"):
                    if depth < max_depth:
                        stack.append((full, depth + 1))
                    continue
                out.append({
                    "name": item.get("name") or full.split("/")[-1],
                    "path": full,
                    "is_dir": False,
                    "size": item.get("size"),
                })
                if len(out) >= max_items:
                    return out
        return out

    def _exists(self, client: Client, remote_path: str) -> bool:
        remote_path = self._norm_rel(remote_path)
        if not remote_path:
            return False
        try:
            if client.check(remote_path):
                return True
        except Exception:
            pass
        try:
            parent = str(Path(remote_path).parent).replace("\\", "/")
            parent = "" if parent == "." else parent
            name = Path(remote_path).name
            items = client.list(parent or "/") or []
            for it in items:
                if it is None:
                    continue
                clean = str(it).rstrip("/")
                if clean.split("/")[-1] == name:
                    return True
        except Exception:
            pass
        return False

    def _ensure_dir(self, client: Client, remote_dir: str) -> None:
        remote_dir = self._norm_rel(remote_dir)
        if not remote_dir:
            return
        parts = remote_dir.split("/")
        cur = ""
        for part in parts:
            cur = f"{cur}/{part}" if cur else part
            try:
                client.mkdir(cur)
            except Exception:
                pass

    def _resolve_conflict(
        self,
        client: Client,
        remote_path: str,
        policy: str,
    ) -> tuple[str, str]:
        """返回 (final_remote_path, action) action=upload|skip|rename|overwrite"""
        policy = (policy or "rename").lower()
        exists = self._exists(client, remote_path)
        if not exists:
            return remote_path, "upload"

        if policy == "overwrite":
            return remote_path, "overwrite"
        if policy == "skip":
            return remote_path, "skip"

        p = Path(remote_path)
        parent = str(p.parent).replace("\\", "/")
        parent = "" if parent == "." else parent
        stem, ext = p.stem, p.suffix
        i = 1
        while True:
            candidate_name = f"{stem} ({i}){ext}"
            candidate = f"{parent}/{candidate_name}" if parent else candidate_name
            if not self._exists(client, candidate):
                return candidate, "rename"
            i += 1
            if i > 9999:
                raise RuntimeError("无法生成可用的远程文件名")

    def _upload_one(
        self,
        client: Client,
        local_path: str,
        remote_path: str,
        policy: str,
    ) -> dict[str, Any]:
        if not local_path or not Path(local_path).exists():
            return {
                "local_path": local_path,
                "remote_path": None,
                "action": "missing",
                "ok": False,
            }
        final_path, action = self._resolve_conflict(client, remote_path, policy)
        if action == "skip":
            return {
                "local_path": local_path,
                "remote_path": final_path,
                "action": "skip",
                "ok": True,
            }
        parent = str(Path(final_path).parent).replace("\\", "/")
        self._ensure_dir(client, parent)
        client.upload_sync(remote_path=final_path, local_path=local_path)
        return {
            "local_path": local_path,
            "remote_path": final_path,
            "action": action if action != "upload" else "uploaded",
            "ok": True,
        }

    def upload_song(
        self,
        song: Song,
        *,
        source_id: int | None = None,
        local_path: str | None = None,
        task_id: int | None = None,
        progress_cb: ProgressCb = None,
        policy: str | None = None,
    ) -> dict[str, Any]:
        if not self.db:
            raise ValueError("WebDAVService 需要数据库会话")
        try:
            selected_file = None
            if local_path:
                selected_file = (
                    self.db.query(SongFile)
                    .filter(SongFile.song_id == song.id, SongFile.local_path == local_path)
                    .first()
                )
            if selected_file is None:
                selected_file = SongFileResolver(self.db).resolve_local(song)
        except NoPlayableSongFileError as exc:
            raise ValueError(str(exc)) from exc
        audio_path = selected_file.local_path
        if not audio_path or not Path(audio_path).exists():
            raise ValueError("本地音频文件不存在")

        # Resolve target source
        target_source: MediaSource | None = None
        if source_id is not None:
            target_source = self.db.get(MediaSource, source_id)
            if not target_source or target_source.type != "webdav":
                raise ValueError("指定的上传源不是 WebDAV 源")
        elif self._get_source() and self._get_source().type == "webdav":
            target_source = self._get_source()
        else:
            target_source = (
                self.db.query(MediaSource)
                .filter(
                    MediaSource.type == "webdav",
                    MediaSource.is_default_upload == True,
                    MediaSource.enabled == True,
                )
                .order_by(MediaSource.id.asc())
                .first()
            )

        if target_source and (target_source.webdav_url or "").strip():
            root_url, _ = self._split_root_and_path(target_source.webdav_url)
            client = self._client(root_url=root_url)
            base = self._remote_base_dir()
            policy = (policy or target_source.conflict_policy or "rename").lower()
            upload_sidecar = bool(target_source.upload_sidecar)
            delete_local = bool(target_source.delete_local_after_upload)
            target_source_id = target_source.id
        else:
            cfg = self._get_config()
            root_url, _ = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)
            base = self._remote_base_dir(cfg)
            policy = (policy or getattr(cfg, "webdav_conflict_policy", None) or "rename").lower()
            upload_sidecar = bool(getattr(cfg, "webdav_upload_sidecar", True))
            delete_local = bool(getattr(cfg, "webdav_delete_local_after_upload", False))
            target_source_id = None

        client.check = lambda p: True

        audio_name = Path(audio_path).name
        audio_remote = self._join_remote(base, audio_name)
        self._ensure_dir(client, base)

        def note(msg: str):
            if progress_cb:
                progress_cb(msg)

        note(f"上传音频: {audio_name}")
        audio_res = self._upload_one(client, audio_path, audio_remote, policy)
        if not audio_res["ok"] and audio_res["action"] != "skip":
            write_log(
                self.db,
                action="upload",
                target="webdav",
                status="failed",
                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                message="音频上传失败",
                local_path=audio_path,
                song_id=song.id,
                task_id=task_id,
                detail={"audio": audio_res},
            )
            raise RuntimeError("音频上传失败")

        final_audio_remote = audio_res["remote_path"] or audio_remote
        final_stem = Path(final_audio_remote).stem
        remote_parent = str(Path(final_audio_remote).parent).replace("\\", "/")
        if remote_parent == ".":
            remote_parent = base

        cover_res = {"action": "disabled", "ok": True, "remote_path": None, "local_path": song.cover_path}
        lrc_res = {"action": "disabled", "ok": True, "remote_path": None, "local_path": song.lrc_path}

        if upload_sidecar:
            cover_local = selected_file.cover_path or song.cover_path
            lrc_local = selected_file.lrc_path or song.lrc_path
            if cover_local and Path(cover_local).exists():
                cover_ext = Path(cover_local).suffix or ".jpg"
                cover_remote = self._join_remote(remote_parent, f"{final_stem}{cover_ext}")
                note(f"上传封面: {Path(cover_remote).name}")
                cover_res = self._upload_one(client, cover_local, cover_remote, policy)
            else:
                cover_res = {"action": "missing", "ok": True, "remote_path": None, "local_path": cover_local}

            if lrc_local and Path(lrc_local).exists():
                lrc_remote = self._join_remote(remote_parent, f"{final_stem}.lrc")
                note(f"上传歌词: {Path(lrc_remote).name}")
                lrc_res = self._upload_one(client, lrc_local, lrc_remote, policy)
            else:
                lrc_res = {"action": "missing", "ok": True, "remote_path": None, "local_path": lrc_local}

        deleted_local = False
        delete_detail: dict[str, Any] = {}
        audio_action = audio_res.get("action")
        truly_uploaded = audio_action in {"uploaded", "overwrite", "rename"}

        if delete_local and truly_uploaded:
            deleted_local, delete_detail = self._delete_local_files(selected_file)
            note("已删除本地文件" if deleted_local else "删除本地文件时部分失败")
        elif delete_local and audio_action == "skip":
            note("远端已存在且策略为跳过，保留本地文件")

        if truly_uploaded or audio_action == "skip":
            selected_file.webdav_path = final_audio_remote
            selected_file.library_source_id = target_source_id or selected_file.library_source_id
            if deleted_local:
                selected_file.local_path = None
                selected_file.cover_path = None
                selected_file.lrc_path = None
            versions = self.db.query(SongFile).filter(SongFile.song_id == song.id).all()
            has_local = any(sf.local_path for sf in versions)
            has_remote = any(sf.webdav_path for sf in versions)
            song.status = "both" if has_local and has_remote else "local" if has_local else "remote"
            if target_source_id:
                song.library_source_id = target_source_id
            from datetime import datetime, timezone
            song.updated_at = datetime.now(timezone.utc)
            self.db.commit()

        overall = "success"
        if audio_action == "skip":
            overall = "skipped"
        elif audio_action == "rename":
            overall = "renamed"
        elif not cover_res.get("ok", True) or not lrc_res.get("ok", True):
            overall = "partial"

        result = {
            "audio": audio_res,
            "cover": cover_res,
            "lrc": lrc_res,
            "webdav_path": final_audio_remote,
            "deleted_local": deleted_local,
            "delete_detail": delete_detail,
            "conflict_policy": policy,
            "status": overall,
        }

        write_log(
            self.db,
            action="upload",
            target="webdav",
            status=overall if overall != "renamed" else "success",
            title=f"{song.artist or ''} - {song.title}".strip(" -"),
            message=self._summarize_upload(result),
            local_path=audio_res.get("local_path"),
            remote_path=final_audio_remote,
            song_id=song.id,
            task_id=task_id,
            detail=result,
        )
        if deleted_local:
            write_log(
                self.db,
                action="delete",
                target="local",
                status="success" if delete_detail.get("ok", True) else "partial",
                title=f"{song.artist or ''} - {song.title}".strip(" -"),
                message="上传后删除本地文件",
                local_path=audio_res.get("local_path"),
                remote_path=final_audio_remote,
                song_id=song.id,
                task_id=task_id,
                detail=delete_detail,
            )
        return result

    def check_conflicts(
        self,
        song: Song,
        *,
        source_id: int | None = None,
        local_path: str | None = None,
    ) -> dict[str, Any]:
        """检查上传目标路径是否已存在同名文件，返回冲突信息供前端确认。"""
        if not self.db:
            raise ValueError("WebDAVService 需要数据库会话")

        selected_file = None
        if local_path:
            selected_file = (
                self.db.query(SongFile)
                .filter(SongFile.song_id == song.id, SongFile.local_path == local_path)
                .first()
            )
        if selected_file is None:
            selected_file = SongFileResolver(self.db).resolve_local(song)
        audio_path = selected_file.local_path
        if not audio_path or not Path(audio_path).exists():
            raise ValueError("本地音频文件不存在")

        # Resolve target source (mirrors upload_song logic)
        target_source: MediaSource | None = None
        if source_id is not None:
            target_source = self.db.get(MediaSource, source_id)
            if not target_source or target_source.type != "webdav":
                raise ValueError("指定的上传源不是 WebDAV 源")
        elif self._get_source() and self._get_source().type == "webdav":
            target_source = self._get_source()
        else:
            target_source = (
                self.db.query(MediaSource)
                .filter(
                    MediaSource.type == "webdav",
                    MediaSource.is_default_upload == True,
                    MediaSource.enabled == True,
                )
                .order_by(MediaSource.id.asc())
                .first()
            )

        if target_source and (target_source.webdav_url or "").strip():
            root_url, _ = self._split_root_and_path(target_source.webdav_url)
            client = self._client(root_url=root_url)
            base = self._remote_base_dir()
            policy = (target_source.conflict_policy or "rename").lower()
            upload_sidecar = bool(target_source.upload_sidecar)
            target_source_id = target_source.id
        else:
            cfg = self._get_config()
            root_url, _ = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)
            base = self._remote_base_dir(cfg)
            policy = (getattr(cfg, "webdav_conflict_policy", None) or "rename").lower()
            upload_sidecar = bool(getattr(cfg, "webdav_upload_sidecar", True))
            target_source_id = None

        client.check = lambda p: True

        audio_name = Path(audio_path).name
        audio_remote = self._join_remote(base, audio_name)

        def _check(local_path: str | None, remote_path: str, kind: str) -> dict[str, Any] | None:
            if not local_path or not Path(local_path).exists():
                return None
            exists = self._exists(client, remote_path)
            return {
                "kind": kind,
                "local_path": local_path,
                "remote_path": remote_path,
                "exists": exists,
            }

        files = [_check(audio_path, audio_remote, "audio")]
        if upload_sidecar:
            cover_local = selected_file.cover_path or song.cover_path
            lrc_local = selected_file.lrc_path or song.lrc_path
            if cover_local and Path(cover_local).exists():
                cover_ext = Path(cover_local).suffix or ".jpg"
                cover_remote = self._join_remote(base, f"{Path(audio_remote).stem}{cover_ext}")
                files.append(_check(cover_local, cover_remote, "cover"))
            if lrc_local and Path(lrc_local).exists():
                lrc_remote = self._join_remote(base, f"{Path(audio_remote).stem}.lrc")
                files.append(_check(lrc_local, lrc_remote, "lrc"))

        files = [item for item in files if item]
        return {
            "target_source_id": target_source_id,
            "target_source_name": target_source.name if target_source else None,
            "policy": policy,
            "conflicts": [item for item in files if item["exists"]],
            "files": files,
        }

    @staticmethod
    def _summarize_upload(result: dict[str, Any]) -> str:
        audio = result.get("audio") or {}
        parts = [f"音频:{audio.get('action')}"]
        for key, label in (("cover", "封面"), ("lrc", "歌词")):
            item = result.get(key) or {}
            parts.append(f"{label}:{item.get('action')}")
        if result.get("deleted_local"):
            parts.append("已删本地")
        return "；".join(parts)

    def _delete_local_files(self, song_file: SongFile) -> tuple[bool, dict[str, Any]]:
        detail: dict[str, Any] = {"files": []}
        ok = True
        for label, path in (
            ("audio", song_file.local_path),
            ("cover", song_file.cover_path),
            ("lrc", song_file.lrc_path),
        ):
            if not path:
                detail["files"].append({"kind": label, "path": path, "action": "missing"})
                continue
            p = Path(path)
            try:
                if p.exists():
                    p.unlink()
                    detail["files"].append({"kind": label, "path": path, "action": "deleted"})
                else:
                    detail["files"].append({"kind": label, "path": path, "action": "missing"})
            except Exception as e:
                ok = False
                detail["files"].append({"kind": label, "path": path, "action": "failed", "error": str(e)})
        detail["ok"] = ok
        return ok, detail

    def download_bytes(self, path: str, *, max_bytes: int = 12 * 1024 * 1024) -> bytes:
        """同步下载远程文件内容（用于封面/侧车缓存）。"""
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, base_dir = self._split_root_and_path(source.webdav_url)
            client = self._client(root_url)
        else:
            cfg = self._get_config()
            root_url, base_dir = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url)
        rel = self._norm_rel(path)
        remote_path = f"{base_dir}/{rel}" if base_dir and rel else (base_dir or rel)
        remote_path = remote_path.strip("/")
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            client.download_sync(remote_path=remote_path, local_path=tmp_path)
            data = Path(tmp_path).read_bytes()
            if max_bytes and len(data) > max_bytes:
                raise ValueError(f"remote file too large: {len(data)} bytes")
            return data
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def stream(self, path: str, range_header: str | None) -> StreamingResponse:
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, base_dir = self._split_root_and_path(source.webdav_url)
            password = decrypt_text(source.webdav_password_enc) or ""
            username = source.webdav_username or ""
        else:
            cfg = self._get_config()
            root_url, base_dir = self._split_root_and_path(cfg.webdav_url)
            password = decrypt_text(cfg.webdav_password_enc) or ""
            username = cfg.webdav_username or ""

        rel = self._norm_rel(path)
        remote_path = f"{base_dir}/{rel}" if base_dir and rel else (base_dir or rel)
        encoded_path = quote(remote_path, safe="/")
        url = root_url.rstrip("/") + "/" + encoded_path.lstrip("/")

        headers = {}
        if range_header:
            headers["Range"] = range_header

        auth = None
        if username:
            auth = aiohttp.BasicAuth(username, password)

        session = aiohttp.ClientSession()
        resp = await session.get(url, headers=headers, auth=auth)

        async def generate():
            try:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    yield chunk
            finally:
                resp.close()
                await session.close()

        media_type = "application/octet-stream"
        ext = os.path.splitext(rel or path or "")[1].lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
        }
        media_type = mime_map.get(ext, media_type)

        out_headers = {}
        if "Content-Range" in resp.headers:
            out_headers["Content-Range"] = resp.headers["Content-Range"]
        if "Content-Length" in resp.headers:
            out_headers["Content-Length"] = resp.headers["Content-Length"]
        if "Accept-Ranges" in resp.headers:
            out_headers["Accept-Ranges"] = resp.headers["Accept-Ranges"]

        return StreamingResponse(
            generate(),
            status_code=resp.status,
            media_type=media_type,
            headers=out_headers,
        )


    def _abs_remote(self, path: str | None) -> str:
        """Join remote base dir with relative path, return absolute remote path for client."""
        rel = self._norm_rel(path)
        base = self._remote_base_dir()
        full = self._join_remote(base, rel)
        return "/" + full if full else "/"

    def exists_path(self, path: str) -> bool:
        """Check whether a remote relative path exists."""
        client = None
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, _ = self._split_root_and_path(source.webdav_url)
            client = self._client(root_url=root_url)
        else:
            cfg = self._get_config()
            root_url, _ = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)
        remote = self._abs_remote(path)
        try:
            # easywebdav / webdav3 style
            if hasattr(client, "check"):
                return bool(client.check(remote))
            if hasattr(client, "exists"):
                return bool(client.exists(remote))
            # fallback: try ls parent
            parent = "/".join(remote.rstrip("/").split("/")[:-1]) or "/"
            name = remote.rstrip("/").split("/")[-1]
            entries = client.ls(parent) if hasattr(client, "ls") else []
            for e in entries or []:
                en = getattr(e, "name", None) or (e.get("name") if isinstance(e, dict) else None) or str(e)
                en = str(en).rstrip("/").split("/")[-1]
                if en == name:
                    return True
            return False
        except Exception:
            return False

    def _ensure_remote_dirs(self, client, remote_file_path: str) -> None:
        """Create parent directories for remote_file_path if needed."""
        parts = [p for p in remote_file_path.strip("/").split("/") if p]
        if len(parts) <= 1:
            return
        cur = ""
        for part in parts[:-1]:
            cur = f"{cur}/{part}"
            try:
                if hasattr(client, "mkdir"):
                    client.mkdir(cur)
            except Exception:
                # already exists or not supported
                pass

    def move_path(self, src: str, dst: str) -> None:
        """Move remote relative path src -> dst (overwrite not guaranteed; unique not handled)."""
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, _ = self._split_root_and_path(source.webdav_url)
            client = self._client(root_url=root_url)
        else:
            cfg = self._get_config()
            root_url, _ = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)

        remote_src = self._abs_remote(src)
        remote_dst = self._abs_remote(dst)
        if remote_src.rstrip("/") == remote_dst.rstrip("/"):
            return
        self._ensure_remote_dirs(client, remote_dst)

        # avoid overwrite: if exists, add suffix
        if self.exists_path(dst):
            stem, ext = Path(dst).stem, Path(dst).suffix
            parent = "/".join(self._norm_rel(dst).split("/")[:-1])
            i = 1
            while True:
                cand = f"{stem}_{i}{ext}"
                cand_rel = f"{parent}/{cand}" if parent else cand
                if not self.exists_path(cand_rel):
                    dst = cand_rel
                    remote_dst = self._abs_remote(dst)
                    break
                i += 1

        if hasattr(client, "move"):
            client.move(remote_src, remote_dst)
            return
        # fallback copy+delete
        if hasattr(client, "copy") and hasattr(client, "delete"):
            client.copy(remote_src, remote_dst)
            client.delete(remote_src)
            return
        raise RuntimeError("WebDAV 客户端不支持 move/copy")

    def copy_path(self, src: str, dst: str) -> None:
        """Copy remote relative path src -> dst."""
        source = self._get_source()
        if source and (source.webdav_url or "").strip():
            root_url, _ = self._split_root_and_path(source.webdav_url)
            client = self._client(root_url=root_url)
        else:
            cfg = self._get_config()
            root_url, _ = self._split_root_and_path(cfg.webdav_url)
            client = self._client(root_url=root_url)

        remote_src = self._abs_remote(src)
        remote_dst = self._abs_remote(dst)
        if remote_src.rstrip("/") == remote_dst.rstrip("/"):
            return
        self._ensure_remote_dirs(client, remote_dst)
        if self.exists_path(dst):
            return
        if hasattr(client, "copy"):
            client.copy(remote_src, remote_dst)
            return
        raise RuntimeError("WebDAV 客户端不支持 copy")

