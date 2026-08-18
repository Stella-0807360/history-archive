import os
import re
import time
import urllib.parse

from .. import db

SESSION_EXTS = (".json",)


def domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc
    except Exception:
        return ""


def safe_name(url):
    d = domain_of(url)
    return re.sub(r"[^0-9A-Za-z.\-]", "_", d) or "site"


def session_path(site):
    if site.get("session_file"):
        return site["session_file"]
    return os.path.join(db.SESS_DIR, safe_name(site.get("url", "site")) + ".json")


def has_session(site):
    return bool(site.get("session_file")) and os.path.exists(site["session_file"])


def save_session_state(context, site):
    path = session_path(site)
    context.storage_state(path=path)
    conn = db.get_conn()
    try:
        conn.execute("UPDATE sites SET session_file=?, updated_at=? WHERE id=?",
                     (path, int(time.time() * 1000), site["id"]))
        conn.commit()
    finally:
        conn.close()
    return path
