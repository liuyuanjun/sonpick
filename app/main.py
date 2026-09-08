import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import logging
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import init_db
from app.routers import auth, download, library, library_extra, library_scan, logs, playlists, search, settings, sources, tasks, webdav
from app.services.task_worker import worker, ws_manager
from app.security import decode_token

APP_VERSION = "0.15.1-rc11"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

DEFAULT_SECRET = "change-me-in-production"


def _warn_insecure_secret() -> None:
    """SECRET_KEY 是 JWT 签名与 WebDAV 密码加密的根密钥；保持默认值会不安全。"""
    key = get_settings().secret_key
    if key == DEFAULT_SECRET or len(key) < 16:
        logging.warning(
            "=" * 60 + "\n"
            "[安全警告] SECRET_KEY 仍为默认值或过短。\n"
            "JWT 签名与已存储的 WebDAV 密码均依赖此密钥。\n"
            "请在 .env 中设置一个 32 字符以上的随机字符串后重启。\n"
            "注意：修改 SECRET_KEY 后，已存储的 WebDAV 密码将无法解密，需重新填写。\n"
            + "=" * 60
        )



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _warn_insecure_secret()
    loop = asyncio.get_running_loop()
    worker.set_loop(loop)
    process_task = asyncio.create_task(worker.process_loop())
    watchdog_task = asyncio.create_task(worker._watchdog())
    yield
    worker.stop()
    process_task.cancel()
    watchdog_task.cancel()


app = FastAPI(title="拾音 Sonpick", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_version_header(request, call_next):
    response = await call_next(request)
    response.headers["X-App-Version"] = APP_VERSION
    return response

@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


app.include_router(auth.router, prefix="/api/auth")
app.include_router(settings.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(download.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(library.router, prefix="/api")
app.include_router(library_extra.router, prefix="/api")
app.include_router(library_scan.router, prefix="/api")
app.include_router(playlists.router, prefix="/api")
app.include_router(webdav.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(logs.router, prefix="/api")


@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket, token: str = Query(...)):
    try:
        decode_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# 前端静态文件
web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if web_dist.exists():
    app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")
    # 品牌静态资源（logo / 图标 / 吉祥物）。必须挂在 SPA catch-all 之前，
    # 否则 /brand/* 会被 /{full_path:path} 兜走返回 index.html，
    # 表现为「图片 200 但显示不出来」。
    brand_dir = web_dist / "brand"
    if brand_dir.exists():
        app.mount("/brand", StaticFiles(directory=brand_dir), name="brand")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # 带扩展名的请求按静态资源处理：缺失时返回 404，
        # 避免「文件不存在」被 200 + index.html 掩盖，难以排查。
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="Not Found")
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"detail": "Frontend not built"}
