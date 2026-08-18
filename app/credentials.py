import json
import os
import time

from cryptography.fernet import Fernet

from . import db


def _load_fernet():
    if not os.path.exists(db.KEY_PATH):
        key = Fernet.generate_key()
        with open(db.KEY_PATH, "wb") as f:
            f.write(key)
    with open(db.KEY_PATH, "rb") as f:
        return Fernet(f.read())


def encrypt_text(text):
    return _load_fernet().encrypt(text.encode("utf-8")).decode()


def decrypt_text(token):
    return _load_fernet().decrypt(token.encode("utf-8")).decode()


def save_creds(site_id, username, password):
    """加密保存站点账号密码，明文不落盘。"""
    payload = json.dumps({"u": username or "", "p": password or ""}, ensure_ascii=False)
    conn = db.get_conn()
    try:
        conn.execute("UPDATE sites SET cred_enc=?, updated_at=? WHERE id=?",
                     (encrypt_text(payload), int(time.time() * 1000), site_id))
        conn.commit()
    finally:
        conn.close()


def get_creds(site_id):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT cred_enc FROM sites WHERE id=?", (site_id,)).fetchone()
    finally:
        conn.close()
    if not row or not row["cred_enc"]:
        return None
    try:
        data = json.loads(decrypt_text(row["cred_enc"]))
        return {"username": data.get("u", ""), "password": data.get("p", "")}
    except Exception:
        return None


def has_creds(site_id):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT cred_enc FROM sites WHERE id=?", (site_id,)).fetchone()
        return bool(row and row["cred_enc"])
    finally:
        conn.close()
