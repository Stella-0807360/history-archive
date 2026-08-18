import hashlib
import hmac
import os
import secrets

from fastapi import Header, HTTPException, Request

from . import db

PW_KEY = "access_pw"          # salt:salt_hex:hash_hex
TOKEN_KEY = "access_token"


def _hash_pw(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return "{}:{}".format(salt, digest.hex())


def has_password():
    return bool(db.get_setting(PW_KEY))


def verify_password(password):
    stored = db.get_setting(PW_KEY)
    if not stored:
        return True  # 未设口令则放行
    salt, expected = stored.split(":")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return hmac.compare_digest(digest.hex(), expected)


def set_password(password):
    db.set_setting(PW_KEY, _hash_pw(password))
    db.set_setting(TOKEN_KEY, secrets.token_hex(24))
    return db.get_setting(TOKEN_KEY)


def issue_token():
    if not db.get_setting(TOKEN_KEY):
        db.set_setting(TOKEN_KEY, secrets.token_hex(24))
    return db.get_setting(TOKEN_KEY)


def check_token(token):
    if not token:
        return False
    if not has_password():
        return True
    stored = db.get_setting(TOKEN_KEY)
    return bool(stored) and hmac.compare_digest(token, stored)


def require_auth(x_auth_token: str = Header(default="")):
    if not check_token(x_auth_token):
        raise HTTPException(status_code=401, detail="需要访问口令")
    return True
