from fastapi import APIRouter

from .. import auth, db

router = APIRouter(prefix="/api/auth")


@router.get("/status")
def status():
    return {"has_password": auth.has_password()}


@router.post("/setup")
def setup(payload: dict):
    """首次设置访问口令。若已设置则忽略。"""
    if auth.has_password():
        return {"ok": False, "msg": "口令已设置，请使用「修改口令」"}
    password = payload.get("password", "")
    if len(password) < 4:
        return {"ok": False, "msg": "口令至少 4 位"}
    token = auth.set_password(password)
    return {"ok": True, "token": token}


@router.post("/login")
def login(payload: dict):
    if not auth.verify_password(payload.get("password", "")):
        return {"ok": False, "msg": "口令错误"}
    return {"ok": True, "token": auth.issue_token()}


@router.post("/change")
def change(payload: dict):
    if not auth.verify_password(payload.get("old_password", "")):
        return {"ok": False, "msg": "原口令错误"}
    new_pw = payload.get("new_password", "")
    if len(new_pw) < 4:
        return {"ok": False, "msg": "新口令至少 4 位"}
    token = auth.set_password(new_pw)
    return {"ok": True, "token": token}
