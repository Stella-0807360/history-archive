import json

from fastapi import APIRouter, Depends, HTTPException

from .. import analysis, credentials, db
from ..auth import require_auth
from ..scraper import generic, login

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


def _site_dict(row):
    d = dict(row)
    d["has_creds"] = bool(d.get("cred_enc"))
    d["has_session"] = bool(d.get("session_file"))
    d.pop("cred_enc", None)
    return d


# ---------------- 站点管理 ----------------

@router.get("/sites")
def list_sites():
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM sites ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = _site_dict(r)
            d["login"] = login.login_status(d["id"])
            d["crawl"] = generic.crawl_status(d["id"])
            out.append(d)
        return {"sites": out}
    finally:
        conn.close()


@router.post("/sites")
def create_site(payload: dict):
    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()
    if not name or not url:
        raise HTTPException(400, "名称与网址不能为空")
    if not url.startswith("http"):
        url = "http://" + url
    conn = db.get_conn()
    try:
        sid = db.new_id("site")
        conn.execute("INSERT INTO sites(id,name,url,note,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (sid, name, url, payload.get("note", ""), "unknown",
                      int(__import__("time").time() * 1000),
                      int(__import__("time").time() * 1000)))
        conn.commit()
        return {"ok": True, "id": sid}
    finally:
        conn.close()


@router.put("/sites/{sid}")
def update_site(sid: str, payload: dict):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "站点不存在")
        url = (payload.get("url") or row["url"]).strip()
        if url and not url.startswith("http"):
            url = "http://" + url
        conn.execute("UPDATE sites SET name=?, url=?, note=?, updated_at=? WHERE id=?",
                     (payload.get("name") or row["name"], url,
                      payload.get("note", row["note"]),
                      int(__import__("time").time() * 1000), sid))
        conn.commit()
    finally:
        conn.close()
    if "username" in payload or "password" in payload:
        credentials.save_creds(sid, payload.get("username", ""), payload.get("password", ""))
    return {"ok": True}


@router.delete("/sites/{sid}")
def delete_site(sid: str):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT session_file FROM sites WHERE id=?", (sid,)).fetchone()
        if row and row["session_file"]:
            import os
            try:
                if os.path.exists(row["session_file"]):
                    os.remove(row["session_file"])
            except OSError:
                pass
        conn.execute("DELETE FROM sites WHERE id=?", (sid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------- 登录 ----------------

@router.post("/crawl/login")
def do_login(payload: dict):
    return login.start_login(payload.get("site_id", ""))


@router.post("/crawl/login/cancel")
def cancel_login(payload: dict):
    return login.cancel_login(payload.get("site_id", ""))


@router.get("/crawl/login/status")
def login_status(site_id: str = ""):
    return login.login_status(site_id)


# ---------------- 抓取 ----------------

@router.post("/crawl/run")
def run_crawl(payload: dict):
    return generic.start_crawl(payload)


@router.post("/crawl/cancel")
def cancel_crawl(payload: dict):
    return generic.cancel_crawl(payload.get("site_id", ""))


@router.get("/crawl/status")
def crawl_status(site_id: str = ""):
    return generic.crawl_status(site_id)


@router.get("/crawl/preview")
def crawl_preview(site_id: str = ""):
    recs = generic.preview(site_id)
    return {"total": len(recs), "records": recs[:200]}


@router.post("/crawl/import")
def crawl_import(payload: dict):
    site_id = payload.get("site_id", "")
    recs = generic.preview(site_id)
    if not recs:
        raise HTTPException(400, "没有可导入的数据")
    conn = db.get_conn()
    try:
        for rec in recs:
            rec["keywords"] = analysis.extract_record_keywords(
                rec.get("title", "") + rec.get("content", ""), 8)
        report = db.add_records(conn, recs, label="抓取导入")
        return {"ok": True, "report": report}
    finally:
        conn.close()


# ---------------- 关联词分析 ----------------

@router.post("/crawl/analyze")
def analyze(payload: dict):
    site_id = payload.get("site_id", "")
    keyword = payload.get("keyword", "")
    recs = generic.preview(site_id)
    if not recs:
        raise HTTPException(400, "请先抓取内容再分析")
    words = analysis.analyze(keyword, recs, int(payload.get("top_n", 60)))
    cloud = analysis.word_cloud_data(words)
    return {"words": words, "cloud": cloud}
