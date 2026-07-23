import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import init_db
from app.routers import auth, download, library, library_extra, library_scan, logs, playlists, search, settings, sources, tasks, webdav
from app.services.task_worker import worker, ws_manager
from app.security import decode_token

APP_VERSION = "0.10.0-rc3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    loop = asyncio.get_event_loop()
    worker.set_loop(loop)
    process_task = asyncio.create_task(worker.process_loop())
    watchdog_task = asyncio.create_task(worker._watchdog())
    yield
    worker.stop()
    process_task.cancel()
    watchdog_task.cancel()


app = FastAPI(title="拾音 Sonpick", lifespan=lifespan)

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

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        index = web_dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"detail": "Frontend not built"}
