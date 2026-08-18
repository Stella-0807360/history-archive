import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import auth, crawl, export, records

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")


def create_app():
    db.init_db()
    app = FastAPI(title="历史资料智能抓取平台", version="1.0.0")
    app.include_router(auth.router)
    app.include_router(records.router)
    app.include_router(crawl.router)
    app.include_router(export.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/api/health")
    def health():
        return {"ok": True, "total": db.count_records(db.get_conn()),
                "pw": bool(db.get_setting("access_pw"))}

    return app


app = create_app()
