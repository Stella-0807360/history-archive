import time

from .. import credentials, db
from . import base, session


def _find_site(site_id):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _auto_fill_login(page, username, password):
    """尝试自动填表登录，返回是否已提交。"""
    try:
        user_sel = "input[name=username], input[name=user], input[name=account], input[name=email], input[type=text][autocomplete=username], input[id*=user], input[name*=user]"
        pw_sel = "input[type=password]"
        page.wait_for_selector(pw_sel, timeout=8000)
        u = page.query_selector(user_sel)
        p = page.query_selector(pw_sel)
        if not p:
            return False
        if u:
            u.fill(username or "")
        p.fill(password or "")
        submit = page.query_selector("button[type=submit], input[type=submit], button:has-text('登 录'), button:has-text('登录'), button:has-text('登入'), button:has-text('Login'), button:has-text('Sign in')")
        if submit:
            submit.click()
        else:
            p.press("Enter")
        return True
    except Exception:
        return False


def _still_on_login(page):
    try:
        return bool(page.query_selector("input[type=password]"))
    except Exception:
        return True


def start_login(site_id):
    site = _find_site(site_id)
    if not site:
        return {"ok": False, "msg": "站点不存在"}
    if base.status_of(base.LOGIN_JOBS, site_id).get("status") == "running":
        return {"ok": False, "msg": "登录任务正在运行中"}
    state = base._init_state(site_id, "login", site_id=site_id, url=site["url"])
    base.LOGIN_JOBS[site_id] = state
    base.start_job(_login_worker, (site,), base.LOGIN_JOBS, state)
    return {"ok": True, "status": "running"}


def cancel_login(site_id):
    return base.cancel(base.LOGIN_JOBS, site_id)


def login_status(site_id):
    return base.status_of(base.LOGIN_JOBS, site_id)


def _login_worker(site, state):
    from playwright.sync_api import sync_playwright
    creds = credentials.get_creds(site["id"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False,
                                     args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 820},
                                  locale="zh-CN")
        pg = ctx.new_page()
        try:
            pg.goto(site["url"], timeout=60000)
        except Exception as e:
            state["message"] = "打开站点失败：" + str(e)
        auto = False
        if creds and creds.get("username") and creds.get("password"):
            auto = _auto_fill_login(pg, creds["username"], creds["password"])
            if auto:
                state["message"] = "已自动填写账号密码并提交，请检查是否登录成功"
        # 等待用户完成登录（自动登录通常几秒内完成，最多 100 秒）
        total = 100
        for i in range(20):
            if state["status"] == "cancelled":
                break
            pg.wait_for_timeout(5000)
            done = auto and not _still_on_login(pg)
            if done:
                state["message"] = "检测到已登录，保存会话…"
                break
            left = total - (i + 1) * 5
            state["message"] = "请在打开的浏览器中完成登录（{}秒后自动保存会话）".format(max(left, 0))
        session.save_session_state(ctx, site)
        state["status"] = "done"
        state["message"] = "登录会话已保存"
        state["found"] = 1
        browser.close()
