from fastapi import APIRouter, Depends, HTTPException

from .. import analysis, db
from ..auth import require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


def _row_to_dict(row):
    d = dict(row)
    for k in ("keywords",):
        import json
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[k] = []
    return d


@router.get("/records")
def search(term: str = "", site_id: str = "", page: int = 1, size: int = 20,
           year_from: str = "", year_to: str = "", sort: str = "created"):
    conn = db.get_conn()
    try:
        where = []
        params = []
        if site_id:
            where.append("site_id=?")
            params.append(site_id)
        if year_from:
            where.append("year>=?")
            params.append(int(year_from))
        if year_to:
            where.append("year<=?")
            params.append(int(year_to))
        term = (term or "").strip()
        order = "created_at DESC"
        if sort == "year":
            order = "year DESC, created_at DESC"
        if term:
            if len(term) >= 3:
                import re
                safe = term.replace('"', '""')
                where.append("id IN (SELECT rowid FROM records_fts WHERE records_fts MATCH ?)")
                params.append('"{}"'.format(safe))
            else:
                like = "%{}%".format(term)
                where.append("(title LIKE ? OR summary LIKE ? OR content LIKE ?)")
                params.extend([like, like, like])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute("SELECT COUNT(*) c FROM records " + where_sql, params).fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM records " + where_sql + " ORDER BY " + order + " LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size]).fetchall()
        items = [_row_to_dict(r) for r in rows]
        sites = conn.execute("SELECT id, name FROM sites").fetchall()
        return {"total": total, "items": items, "sites": [dict(s) for s in sites]}
    finally:
        conn.close()


@router.get("/records/{rid}")
def detail(rid: str):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "记录不存在")
    return _row_to_dict(row)


@router.delete("/records/{rid}")
def remove(rid: str):
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM records WHERE id=?", (rid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/records")
def clear_all():
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM records")
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/stats")
def stats():
    conn = db.get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
        by_site = [dict(r) for r in conn.execute(
            "SELECT site_name v, COUNT(*) n FROM records GROUP BY site_name ORDER BY n DESC").fetchall()]
        by_year = [dict(r) for r in conn.execute(
            "SELECT year v, COUNT(*) n FROM records WHERE year IS NOT NULL GROUP BY year ORDER BY v DESC").fetchall()]
        recent = [dict(r) for r in conn.execute(
            "SELECT * FROM records ORDER BY created_at DESC LIMIT 8").fetchall()]
        logs = [dict(r) for r in conn.execute(
            "SELECT * FROM import_logs ORDER BY created_at DESC LIMIT 20").fetchall()]
        return {"total": total, "by_site": by_site, "by_year": by_year,
                "recent": recent, "logs": logs}
    finally:
        conn.close()


@router.post("/records/keywords")
def record_keywords(payload: dict):
    """对一段文本抽取关键词（用于入库前预览/编辑）。"""
    text = payload.get("text", "")
    n = int(payload.get("n", 8))
    return {"keywords": analysis.extract_record_keywords(text, n)}
