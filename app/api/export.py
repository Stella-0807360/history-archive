import io
import json
import urllib.parse

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .. import db
from ..auth import require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


def _disposition(name):
    return 'attachment; filename="archive"; filename*=UTF-8\'\'{}'.format(
        urllib.parse.quote(name))


def _get_records(ids=None, site_id=""):
    conn = db.get_conn()
    try:
        if ids:
            id_list = [x for x in ids.split(",") if x]
            if not id_list:
                return []
            q = ",".join("?" * len(id_list))
            rows = conn.execute("SELECT * FROM records WHERE id IN ({})".format(q), id_list).fetchall()
        elif site_id:
            rows = conn.execute("SELECT * FROM records WHERE site_id=?", (site_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM records ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["keywords"] = json.loads(d.get("keywords") or "[]")
            except Exception:
                d["keywords"] = []
            out.append(d)
        return out
    finally:
        conn.close()


@router.get("/export")
def export(ids: str = "", site_id: str = "", fmt: str = "txt"):
    recs = _get_records(ids, site_id)
    if fmt == "json":
        body = json.dumps(recs, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": _disposition("抓取资料.json")})
    if fmt == "csv":
        import csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["标题", "来源站", "年份", "链接", "摘要", "正文"])
        for r in recs:
            w.writerow([r.get("title", ""), r.get("site_name", ""), r.get("year") or "",
                        r.get("url", ""), (r.get("summary") or "")[:300],
                        (r.get("content") or "")[:2000]])
        body = ("\ufeff" + buf.getvalue()).encode("utf-8")
        return Response(body, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": _disposition("抓取资料.csv")})
    lines = []
    for r in recs:
        if fmt == "gbt":
            lines.append("{0}[EB/OL]. {1}, {2}. {3}".format(
                r.get("title", ""), r.get("site_name", ""),
                r.get("year") or "n.d.", r.get("url", "")))
        else:
            lines.append("标题：{}".format(r.get("title", "")))
            lines.append("来源：{}  年份：{}".format(r.get("site_name", ""), r.get("year") or ""))
            lines.append("链接：{}".format(r.get("url", "")))
            lines.append("摘要：{}".format((r.get("summary") or "")[:300]))
            lines.append("")
    body = "\n".join(lines).encode("utf-8")
    fn = "抓取资料_GB7714.txt" if fmt == "gbt" else "抓取资料.txt"
    return Response(body, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": _disposition(fn)})


@router.get("/qr")
def qr(text: str = ""):
    import segno
    qr = segno.make(text or "https://example.com")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=1, border=0)
    return Response(buf.getvalue(), media_type="image/svg+xml")
