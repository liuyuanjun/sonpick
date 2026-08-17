from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        # SQLite + 多线程：禁用 QueuePool，避免封面并发/后台任务把连接池打满
        _engine = create_engine(
            f"sqlite:///{settings.database_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            poolclass=NullPool,
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        # 仅在未绑定时配置；测试会用 SessionLocal.configure 绑到临时库，不得覆盖
        if SessionLocal.kw.get("bind") is None:
            SessionLocal.configure(bind=_engine)
    return _engine



def init_db():
    """初始化表结构并执行幂等增量迁移。"""
    engine = get_engine()
    # 确保所有 ORM 模型已注册到 Base.metadata。
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns(engine)
    _migrate_settings_lossy_output(engine)
    _seed_media_sources(engine)
    _ensure_song_file_indexes(engine)
    _migrate_song_path_responsibility(engine)
    _migrate_song_drop_library_source(engine)


def _ensure_columns(engine: Engine):
    """SQLite lightweight additive migrations for existing DBs."""
    specs = {
        "settings": {
            "webdav_delete_local_after_upload": "BOOLEAN DEFAULT 0",
            "webdav_upload_sidecar": "BOOLEAN DEFAULT 1",
            "webdav_conflict_policy": "VARCHAR(16) DEFAULT 'rename'",
            "webdav_remote_dir": "VARCHAR(512) DEFAULT ''",
            "scan_local_enabled": "BOOLEAN DEFAULT 1",
            "scan_local_dirs": "TEXT DEFAULT '[]'",
            "scan_webdav_enabled": "BOOLEAN DEFAULT 1",
            "scan_webdav_dirs": "TEXT DEFAULT '[\"\"]'",
            "scan_exclude_globs": (
                "TEXT DEFAULT "
                "'[\"**/.*\",\"**/.@*\",\"**/@eaDir/**\",\"**/#recycle/**\","
                "\"**/Thumbs.db\",\"**/*.tmp\"]'"
            ),
            "scan_audio_exts": "VARCHAR(255) DEFAULT 'mp3,flac,m4a,wav,ogg,aac,ape,wma'",
            "scrape_sources_json": "TEXT DEFAULT '[]'",
            "lyrics_sources_json": "TEXT DEFAULT '[]'",
            "acoustid_api_key_enc": "VARCHAR(1024)",
            "lossy_output_path": "VARCHAR(512)",
            "lossless_output_path": "VARCHAR(512)",
            "lossless_preferred": "BOOLEAN DEFAULT 0",
            "auto_convert_when_lossless_not_preferred": "BOOLEAN DEFAULT 0",
        },
        "media_sources": {
            "playback_priority": "INTEGER NOT NULL DEFAULT 0",
        },
        "song_files": {
            "source_priority": "INTEGER NOT NULL DEFAULT 0",
            "availability_status": "VARCHAR(16) NOT NULL DEFAULT 'unknown'",
            "last_checked_at": "DATETIME",
            "last_error": "VARCHAR(512)",
            "cover_path": "VARCHAR(1024)",
            "lrc_path": "VARCHAR(1024)",
        },
        "songs": {
            "source_id": "VARCHAR(128)",
            "year": "VARCHAR(16)",
            "genre": "VARCHAR(255)",
            "lyrics_provider": "VARCHAR(64)",
            "lyrics_source_id": "VARCHAR(128)",
            "lyrics_type": "VARCHAR(16)",
            "lyrics_score": "INTEGER",
            "lyrics_fetched_at": "DATETIME",
            "lyrics_instrumental": "BOOLEAN DEFAULT 0",
            "meta_confidence": "INTEGER DEFAULT 0",
            "meta_provider": "VARCHAR(64)",
            "scrape_status": "VARCHAR(16) DEFAULT 'none'",
            "meta_locked": "BOOLEAN DEFAULT 0",
            "play_count": "INTEGER DEFAULT 0",
        },
        "tasks": {
            "worker_thread_id": "INTEGER",
            "started_at": "DATETIME",
        },
    }
    insp = inspect(engine)
    started_at_added = False
    with engine.begin() as conn:
        for table, cols in specs.items():
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    if table == "tasks" and name == "started_at":
                        started_at_added = True

        if started_at_added:
            conn.execute(text(
                "UPDATE tasks SET started_at = created_at WHERE started_at IS NULL"
            ))


def _migrate_settings_lossy_output(engine: Engine):
    """settings.mp3_output_path → lossy_output_path：物化旧生效值后删除旧列。

    旧值为空（一直在用默认目录）时按旧默认 <存储目录>/MP3 物化，保证已有部署的
    落盘目录在升级后不变；新安装由 settings 播种逻辑默认 <存储目录>/LOSSY。
    须在 _ensure_columns 之后运行（新列由它补齐）。
    """
    inspector = inspect(engine)
    if "settings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("settings")}
    if "mp3_output_path" not in columns:
        return

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT storage_path, mp3_output_path, lossy_output_path FROM settings WHERE id = 1")
        ).mappings().first()
        if row and not (row.get("lossy_output_path") or "").strip():
            value = (row.get("mp3_output_path") or "").strip()
            if not value:
                value = str(Path((row.get("storage_path") or "").strip()) / "MP3")
            conn.execute(
                text("UPDATE settings SET lossy_output_path = :value WHERE id = 1"),
                {"value": value},
            )
        # SQLite ≥ 3.35 支持 DROP COLUMN；更老版本保留无害旧列，模型已不再读取
        version = conn.execute(text("SELECT sqlite_version()")).scalar() or "0.0.0"
        if tuple(int(p) for p in version.split(".")[:3]) >= (3, 35, 0):
            conn.execute(text("ALTER TABLE settings DROP COLUMN mp3_output_path"))
            print("[migration] settings.mp3_output_path → lossy_output_path（旧列已删除）", flush=True)
        else:
            print("[migration] settings.mp3_output_path → lossy_output_path（SQLite 过旧，保留旧列）", flush=True)


def _ensure_song_file_indexes(engine: Engine):
    """为 SongFile 版本查询建立幂等索引，SQLite 不支持安全地补唯一约束。"""
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_song_files_song_source_format "
            "ON song_files (song_id, library_source_id, format)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_song_files_webdav_source_path "
            "ON song_files (library_source_id, webdav_path)"
        ))


def _migrate_song_path_responsibility(engine: Engine):
    """一次性、幂等地把旧 songs 物理路径迁移到 SongFile 后删除旧列。"""
    inspector = inspect(engine)
    if "songs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("songs")}
    legacy_columns = {"local_path", "webdav_path"}
    if not legacy_columns.intersection(columns):
        return

    # 先关闭当前短连接的外键检查；重建完成后连接即关闭，设置不会影响其他连接。
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        # 旧库可能尚无 library_source_id 列（取决于历经的版本），查询做自适应
        lib_src_select = ", library_source_id" if "library_source_id" in columns else ""
        rows = conn.execute(text(
            f"SELECT id, format, duration, file_size, local_path, webdav_path, cover_path, lrc_path{lib_src_select} "
            "FROM songs"
        )).mappings().all()
        created = 0
        enriched = 0
        for row in rows:
            local_path = row.get("local_path")
            webdav_path = row.get("webdav_path")
            if not local_path and not webdav_path:
                continue
            existing = conn.execute(text(
                "SELECT id, cover_path, lrc_path FROM song_files "
                "WHERE song_id = :song_id AND "
                "((:local_path IS NOT NULL AND local_path = :local_path) "
                "OR (:webdav_path IS NOT NULL AND webdav_path = :webdav_path)) LIMIT 1"
            ), {
                "song_id": row["id"],
                "local_path": local_path,
                "webdav_path": webdav_path,
            }).mappings().first()
            if existing is None:
                conn.execute(text(
                    "INSERT INTO song_files "
                    "(song_id, format, local_path, webdav_path, cover_path, lrc_path, library_source_id, "
                    "duration, file_size, availability_status, source_priority, created_at, updated_at) "
                    "VALUES (:song_id, :format, :local_path, :webdav_path, :cover_path, :lrc_path, :source_id, "
                    ":duration, :file_size, 'unknown', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ), {
                    "song_id": row["id"],
                    "format": (row.get("format") or "unknown").lower(),
                    "local_path": local_path,
                    "webdav_path": webdav_path,
                    "cover_path": row.get("cover_path"),
                    "lrc_path": row.get("lrc_path"),
                    "source_id": row.get("library_source_id"),
                    "duration": row.get("duration"),
                    "file_size": row.get("file_size"),
                })
                created += 1
            else:
                values = {
                    "id": existing["id"],
                    "cover_path": existing.get("cover_path") or row.get("cover_path"),
                    "lrc_path": existing.get("lrc_path") or row.get("lrc_path"),
                }
                if values["cover_path"] != existing.get("cover_path") or values["lrc_path"] != existing.get("lrc_path"):
                    conn.execute(text(
                        "UPDATE song_files SET cover_path = :cover_path, lrc_path = :lrc_path, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                    ), values)
                    enriched += 1

        # SQLite DROP COLUMN 对旧 SQLite 版本与外键约束不可靠，采用表重建。
        # 同时顺手删除 library_source_id（来源归属统一由 SongFile 承载）。
        kept = [
            "id", "title", "artist", "album", "year", "genre", "source", "source_id", "format", "duration", "file_size",
            "cover_path", "lrc_path", "lyrics_provider", "lyrics_source_id", "lyrics_type", "lyrics_score",
            "lyrics_fetched_at", "lyrics_instrumental", "status", "play_count", "meta_confidence",
            "meta_provider", "scrape_status", "meta_locked", "created_at", "updated_at",
        ]
        definitions = [
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "title VARCHAR(255) NOT NULL",
            "artist VARCHAR(255)", "album VARCHAR(255)", "year VARCHAR(16)", "genre VARCHAR(255)",
            "source VARCHAR(64)", "source_id VARCHAR(128)",
            "format VARCHAR(16)", "duration INTEGER", "file_size INTEGER", "cover_path VARCHAR(1024)",
            "lrc_path VARCHAR(1024)", "lyrics_provider VARCHAR(64)", "lyrics_source_id VARCHAR(128)",
            "lyrics_type VARCHAR(16)", "lyrics_score INTEGER", "lyrics_fetched_at DATETIME", "lyrics_instrumental BOOLEAN DEFAULT 0",
            "status VARCHAR(16)", "play_count INTEGER", "meta_confidence INTEGER", "meta_provider VARCHAR(64)",
            "scrape_status VARCHAR(16)", "meta_locked BOOLEAN", "created_at DATETIME", "updated_at DATETIME",
        ]
        quoted = ", ".join(kept)
        conn.execute(text(f"CREATE TABLE songs__path_migration ({', '.join(definitions)})"))
        conn.execute(text(
            f"INSERT INTO songs__path_migration ({quoted}) SELECT {quoted} FROM songs"
        ))
        conn.execute(text("DROP TABLE songs"))
        conn.execute(text("ALTER TABLE songs__path_migration RENAME TO songs"))
        conn.commit()
        print(f"[migration] SongFile path responsibility: created={created}, enriched={enriched}", flush=True)


def _migrate_song_drop_library_source(engine: Engine):
    """一次性、幂等地从 songs 表删除 library_source_id 列。

    歌曲与来源的归属统一由 SongFile.library_source_id 承载（见 library_visibility）。
    已在路径责任迁移中重建过的新表不含该列，会自动跳过。
    """
    inspector = inspect(engine)
    if "songs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("songs")}
    if "library_source_id" not in columns:
        return

    definitions = {
        "id": "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "title": "title VARCHAR(255) NOT NULL",
        "artist": "artist VARCHAR(255)",
        "album": "album VARCHAR(255)",
        "year": "year VARCHAR(16)",
        "genre": "genre VARCHAR(255)",
        "source": "source VARCHAR(64)",
        "source_id": "source_id VARCHAR(128)",
        "format": "format VARCHAR(16)",
        "duration": "duration INTEGER",
        "file_size": "file_size INTEGER",
        "cover_path": "cover_path VARCHAR(1024)",
        "lrc_path": "lrc_path VARCHAR(1024)",
        "lyrics_provider": "lyrics_provider VARCHAR(64)",
        "lyrics_source_id": "lyrics_source_id VARCHAR(128)",
        "lyrics_type": "lyrics_type VARCHAR(16)",
        "lyrics_score": "lyrics_score INTEGER",
        "lyrics_fetched_at": "lyrics_fetched_at DATETIME",
        "lyrics_instrumental": "lyrics_instrumental BOOLEAN DEFAULT 0",
        "status": "status VARCHAR(16)",
        "play_count": "play_count INTEGER",
        "meta_confidence": "meta_confidence INTEGER",
        "meta_provider": "meta_provider VARCHAR(64)",
        "scrape_status": "scrape_status VARCHAR(16)",
        "meta_locked": "meta_locked BOOLEAN",
        "created_at": "created_at DATETIME",
        "updated_at": "updated_at DATETIME",
    }
    kept = [name for name in definitions if name in columns]
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        quoted = ", ".join(kept)
        conn.execute(text(
            f"CREATE TABLE songs__drop_libsrc ({', '.join(definitions[name] for name in kept)})"
        ))
        conn.execute(text(
            f"INSERT INTO songs__drop_libsrc ({quoted}) SELECT {quoted} FROM songs"
        ))
        conn.execute(text("DROP TABLE songs"))
        conn.execute(text("ALTER TABLE songs__drop_libsrc RENAME TO songs"))
        conn.commit()
        print("[migration] songs.library_source_id dropped; source ownership lives on song_files", flush=True)


def _dump_json_list(items):
    import json

    clean = []
    for x in items or []:
        s = str(x).strip()
        if s not in clean:
            clean.append(s)
    return json.dumps(clean, ensure_ascii=False)


def _seed_media_sources(engine: Engine):
    """Seed default media sources from AppSettings / config if table is empty."""
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models import AppSettings, MediaSource, Song
    from app.routers.settings import DEFAULT_SCAN_EXCLUDE, DEFAULT_SCAN_EXTS, _ensure_settings, _parse_json_list

    cfg = get_settings()
    with Session(engine) as db:
        count = db.query(MediaSource).count()
        if count > 0:
            return

        s = _ensure_settings(db)

        # default local source
        scan_dirs = _parse_json_list(getattr(s, "scan_local_dirs", None), [])
        if not scan_dirs:
            scan_dirs = [""]
        local = MediaSource(
            name="本地曲库",
            type="local",
            enabled=True,
            root_path=s.storage_path or cfg.storage_path,
            scan_dirs=_dump_json_list(scan_dirs),
            exclude_globs=getattr(s, "scan_exclude_globs", None) or _dump_json_list(DEFAULT_SCAN_EXCLUDE),
            audio_exts=getattr(s, "scan_audio_exts", None) or DEFAULT_SCAN_EXTS,
            connection_status="unknown",
        )
        db.add(local)
        db.flush()

        # default webdav source if configured
        webdav_source = None
        if (s.webdav_url or "").strip():
            webdav_source = MediaSource(
                name="WebDAV",
                type="webdav",
                enabled=True,
                webdav_url=s.webdav_url,
                webdav_username=s.webdav_username,
                webdav_password_enc=s.webdav_password_enc,
                remote_dir=getattr(s, "webdav_remote_dir", None) or "",
                scan_remote_dirs=getattr(s, "scan_webdav_dirs", None) or '[""]',
                exclude_globs=getattr(s, "scan_exclude_globs", None) or _dump_json_list(DEFAULT_SCAN_EXCLUDE),
                audio_exts=getattr(s, "scan_audio_exts", None) or DEFAULT_SCAN_EXTS,
                is_default_upload=bool(getattr(s, "auto_upload_webdav", False)),
                upload_sidecar=bool(getattr(s, "webdav_upload_sidecar", True)),
                conflict_policy=getattr(s, "webdav_conflict_policy", None) or "rename",
                delete_local_after_upload=bool(getattr(s, "webdav_delete_local_after_upload", False)),
                connection_status="unknown",
            )
            db.add(webdav_source)
            db.flush()

        db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
