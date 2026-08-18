import hashlib
import json
import os
import re
import sqlite3
import time
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("ARCHIVE_DATA") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "archive.db")
SESS_DIR = os.path.join(DATA_DIR, "sessions")
KEY_PATH = os.path.join(DATA_DIR, ".vault.key")
STOPWORDS_PATH = os.path.join(DATA_DIR, "stopwords.txt")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SESS_DIR, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  note TEXT DEFAULT '',
  cred_enc TEXT DEFAULT '',
  session_file TEXT DEFAULT '',
  status TEXT DEFAULT 'unknown',
  created_at INTEGER,
  updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sites_url ON sites(url);

CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  site_id TEXT DEFAULT '',
  site_name TEXT DEFAULT '',
  title TEXT NOT NULL,
  url TEXT DEFAULT '',
  year INTEGER,
  lang TEXT DEFAULT '中文',
  summary TEXT DEFAULT '',
  content TEXT DEFAULT '',
  keywords TEXT DEFAULT '[]',
  dedup_hash TEXT DEFAULT '',
  created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_records_site ON records(site_id);
CREATE INDEX IF NOT EXISTS idx_records_year ON records(year);
CREATE UNIQUE INDEX IF NOT EXISTS idx_records_dedup ON records(dedup_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  title, summary, content, keywords_text, tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS import_logs (
  id TEXT PRIMARY KEY,
  label TEXT DEFAULT '',
  total INTEGER,
  added INTEGER,
  dup INTEGER,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
  k TEXT PRIMARY KEY,
  v TEXT
);
"""

TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
  INSERT INTO records_fts(rowid, title, summary, content, keywords_text)
  VALUES (new.rowid, new.title, new.summary, new.content, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
  DELETE FROM records_fts WHERE rowid = old.rowid;
END;
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.executescript(TRIGGERS)
        conn.commit()
    finally:
        conn.close()


def new_id(prefix="r"):
    return prefix + "_" + time.strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]


def get_setting(key, default=""):
    conn = get_conn()
    try:
        row = conn.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        return row["v"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO settings(k,v) VALUES(?,?) "
                     "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def _norm(s):
    if not s:
        return ""
    return re.sub(r"[\s\u3000\n\r\t，,。.；;：:\"'“”‘’《》〈〉（）()【】\[\]]", "", str(s))


def dedup_hash(rec):
    key = "|".join([_norm(rec.get("title", "")), _norm(rec.get("url", ""))])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def add_records(conn, recs, label="抓取"):
    now = int(time.time() * 1000)
    added = dup = 0
    for rec in recs:
        rec["id"] = new_id()
        rec["keywords"] = rec.get("keywords") or []
        rec["created_at"] = now
        rec["dedup_hash"] = rec.get("dedup_hash") or dedup_hash(rec)
        cols = ["id", "site_id", "site_name", "title", "url", "year", "lang",
                "summary", "content", "keywords", "dedup_hash", "created_at"]
        values = [rec.get(c) for c in cols]
        for i, c in enumerate(cols):
            v = values[i]
            if isinstance(v, (list, dict)):
                values[i] = json.dumps(v, ensure_ascii=False)
            elif v is None:
                values[i] = ""
        sql = "INSERT INTO records ({}) VALUES ({})".format(",".join(cols), ",".join("?" * len(cols)))
        try:
            conn.execute(sql, values)
            added += 1
        except sqlite3.IntegrityError:
            dup += 1
    conn.commit()
    if label:
        conn.execute("INSERT INTO import_logs(id,label,total,added,dup,created_at) VALUES(?,?,?,?,?,?)",
                     (new_id("log"), label, len(recs), added, dup, now))
        conn.commit()
    return {"total": len(recs), "added": added, "dup": dup}


def count_records(conn):
    return conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]


if __name__ == "__main__":
    init_db()
    print("DB ready:", DB_PATH)
