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

        SessionLocal.configure(bind=_engine)
    return _engine


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
        },
        "songs": {
            "meta_confidence": "INTEGER DEFAULT 0",
            "meta_provider": "VARCHAR(64)",
            "scrape_status": "VARCHAR(16) DEFAULT 'none'",
            "meta_locked": "BOOLEAN DEFAULT 0",
            "play_count": "INTEGER DEFAULT 0",
            "library_source_id": "INTEGER",
        },
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in specs.items():
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db():
    engine = get_engine()
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns(engine)
    _seed_media_sources(engine)


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
            _backfill_song_sources(db)
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
        _backfill_song_sources(db, local_id=local.id, webdav_id=webdav_source.id if webdav_source else None)


def _backfill_song_sources(db, local_id=None, webdav_id=None):
    from app.models import MediaSource, Song

    if local_id is None:
        local = db.query(MediaSource).filter(MediaSource.type == "local").order_by(MediaSource.id.asc()).first()
        local_id = local.id if local else None
    if webdav_id is None:
        webdav = db.query(MediaSource).filter(MediaSource.type == "webdav").order_by(MediaSource.id.asc()).first()
        webdav_id = webdav.id if webdav else None

    songs = db.query(Song).filter(Song.library_source_id.is_(None)).all()
    changed = False
    for song in songs:
        if song.local_path and local_id:
            song.library_source_id = local_id
            changed = True
        elif song.webdav_path and webdav_id:
            song.library_source_id = webdav_id
            changed = True
    if changed:
        db.commit()



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
