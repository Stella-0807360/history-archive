import os
import re
import time
import urllib.parse

from .. import credentials, db
from . import base, session

TITLE_MIN = 4
NEXT_TEXTS = ("下一页", "下页", "后一页", "下一頁", "Next", "下一章", ">")
SEARCH_SELS = ("input[type=search]", "input[name*=q]", "input[name*=key]",
               "input[name*=search]", "input[id*=search]", "input[placeholder*=搜索]",
               "input[placeholder*=输入]", "input[placeholder*=查询]", "textarea[placeholder*=搜索]",
               "input[type=text]")


def _find_site(site_id):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _clean_text(s):
    s = re.sub(r"[\s\u3000]+", " ", str(s or ""))
    return s.strip()


def _year_of(text):
    hits = re.findall(r"(19|20)\d{2}", str(text or ""))
    if not hits:
        return None
    counts = {}
    for h in hits:
        counts[h] = counts.get(h, 0) + 1
    return int(max(counts, key=counts.get))


def _find_search_input(page):
    for sel in SEARCH_SELS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return el
        except Exception:
            continue
    # 兜底：给所有可见输入框打分，选最像搜索框的
    try:
        best, best_score = None, 0
        for el in page.query_selector_all("input, textarea"):
            if not el.is_visible():
                continue
            score = 0
            name = (el.get_attribute("name") or "") + (el.get_attribute("id") or "")
            cls = el.get_attribute("class") or ""
            ph = el.get_attribute("placeholder") or ""
            if re.search(r"search|q\b|keyword|query", name, re.I):
                score += 3
            if re.search(r"search|query", cls, re.I):
                score += 3
            if re.search(r"搜索|查找|查询|检索|输入", ph):
                score += 2
            if el.get_attribute("type") == "search":
                score += 3
            if score > best_score:
                best, best_score = el, score
        return best
    except Exception:
        return None


def _do_search(page, keyword):
    inp = _find_search_input(page)
    if not inp:
        return False
    try:
        inp.fill(keyword)
        submit = page.query_selector("button[type=submit], input[type=submit], button[class*=search], button[class*=Search]")
        if not (submit and submit.is_visible()):
            try:
                for b in page.query_selector_all("button"):
                    txt = _clean_text(b.inner_text())
                    if re.search(r"搜索|查找|查询|检索|搜", txt) and len(txt) <= 6 and b.is_visible():
                        submit = b
                        break
            except Exception:
                submit = None
        if submit and submit.is_visible():
            submit.click()
        else:
            inp.press("Enter")
        return True
    except Exception:
        return False


def _find_next(page):
    try:
        el = page.query_selector("a[rel=next], link[rel=next]")
        if el:
            return el
        for sel in ("a.next", ".pagination .next a", ".next", ".pager a:last-child"):
            e = page.query_selector(sel)
            if e and e.is_visible():
                return e
        anchors = page.query_selector_all("a")
        for a in anchors:
            txt = _clean_text(a.inner_text())
            if any(t in txt for t in NEXT_TEXTS) and len(txt) <= 8:
                return a
    except Exception:
        return None
    return None


_LIST_JS = r"""
() => {
  const stop = ['nav','header','footer','aside'];
  const out = [];
  const anchors = document.querySelectorAll('a[href]');
  for (const a of anchors) {
    const href = (a.getAttribute('href')||'').trim();
    const t = (a.innerText||'').replace(/\s+/g,' ').trim();
    if (t.length < 4 || !href) continue;
    if (/^(javascript:|mailto:|#|tel:)/.test(href)) continue;
    if (/login|register|signup|logout|javascript/i.test(href)) continue;
    let n = a, skip = false;
    for (let i = 0; i < 5 && n; i++) {
      const tag = n.tagName.toLowerCase();
      if (stop.includes(tag) || /(^|\s)(nav|menu|breadcrumb|pagination|footer|header|aside|ad)(\s|$)/.test(n.className||'')) { skip = true; break; }
      n = n.parentElement;
    }
    if (skip) continue;
    if (/首页|登录|注册|关于我们|联系我们|返回首页|免责声明/.test(t)) continue;
    out.push({href, text:t});
  }
  return out;
}
"""


def extract_list(page, limit=300):
    try:
        raw = page.evaluate(_LIST_JS)
    except Exception:
        return []
    seen = {}
    for it in raw:
        if len(seen) >= limit:
            break
        title = _clean_text(it.get("text") or "")
        href = it.get("href") or ""
        url = urllib.parse.urljoin(page.url, href)
        if not url.startswith("http") or url in seen:
            continue
        seen[url] = {"title": title, "url": url}
    return list(seen.values())


_CONTENT_JS = r"""
() => {
  const stop = ['nav','header','footer','aside'];
  const skip = (el) => {
    let n = el;
    for (let i = 0; i < 5 && n; i++) {
      const tag = n.tagName.toLowerCase();
      if (stop.includes(tag) || /(^|\s)(nav|menu|breadcrumb|pagination|footer|header|aside|ad|ads)(\s|$)/.test(n.className||'')) return true;
      n = n.parentElement;
    }
    return false;
  };
  const picks = ['article','main','#content','.content','.article','.post','.detail','.entry','.main-content','.lemma-summary','.article-content','.wpb-content','.news-content','.text-content'];
  for (const sel of picks) {
    let els = [];
    try { els = document.querySelectorAll(sel); } catch (e) {}
    for (const el of els) {
      const t = (el.innerText||'').replace(/\s+/g,' ').trim();
      if (t.length > 300 && !skip(el)) return {content: t};
    }
  }
  const parts = [];
  const all = document.querySelectorAll('p, h1, h2, h3, h4, div');
  for (const el of all) {
    if (el.offsetParent === null) continue;
    if (skip(el)) continue;
    const t = (el.innerText||'').replace(/\s+/g,' ').trim();
    if (t.length < 30) continue;
    if (el.tagName === 'DIV') {
      // 只收集“叶子”文本块，避免容器与子块重复计入
      const kids = el.querySelectorAll('p, h1, h2, h3, h4, div');
      let dup = false;
      for (const k of kids) {
        const kt = (k.innerText||'').replace(/\s+/g,' ').trim();
        if (kt.length >= 30) { dup = true; break; }
      }
      if (dup) continue;
    }
    parts.push(t);
    if (parts.join(' ').length > 200000) break;
  }
  return {content: parts.join(' ')};
}
"""


def extract_content(page):
    """启发式提取正文：优先常见正文容器，兜底按文本密度收集段落（单次 evaluate 完成）。"""
    try:
        res = page.evaluate(_CONTENT_JS)
        text = _clean_text(res.get("content") or "")
    except Exception:
        text = ""
    if len(text) < 80:
        text = ""
    title = ""
    for sel in ("h1",):
        try:
            el = page.query_selector(sel)
            if el:
                t = _clean_text(el.inner_text())
                if t and len(t) <= 100:
                    title = t
                    break
        except Exception:
            continue
    if not title:
        try:
            title = _clean_text(page.title())
        except Exception:
            title = ""
    return {"title": title[:120], "content": text[:200000]}


def _extract_detail(browser, ctx, pg, url):
    try:
        page = ctx.new_page()
        page.goto(url, timeout=45000)
        page.wait_for_timeout(800)
        info = extract_content(page)
        page.close()
        return info
    except Exception:
        return {"title": "", "content": ""}


def start_crawl(params):
    site_id = params.get("site_id", "")
    site = _find_site(site_id)
    if not site:
        return {"ok": False, "msg": "站点不存在"}
    key = "crawl_" + site_id
    if base.status_of(base.JOBS, key).get("status") == "running":
        return {"ok": False, "msg": "抓取任务正在运行中"}
    state = base._init_state(key, "crawl",
                             site_id=site_id, site_url=site["url"],
                             keyword=params.get("keyword", ""),
                             pages=int(params.get("pages", 3)),
                             depth=int(params.get("depth", 1)),
                             max_items=int(params.get("max_items", 50)),
                             site_name=site["name"])
    base.JOBS[key] = state
    base.start_job(_crawl_worker, (site,), base.JOBS, state)
    return {"ok": True, "status": "running"}


def cancel_crawl(site_id):
    return base.cancel(base.JOBS, "crawl_" + site_id)


def crawl_status(site_id):
    return base.status_of(base.JOBS, "crawl_" + site_id)


def preview(site_id):
    return base.preview_of(base.JOBS, "crawl_" + site_id)


def _crawl_worker(site, state):
    from playwright.sync_api import sync_playwright
    keyword = state["keyword"]
    pages = state["pages"]
    depth = state["depth"]
    max_items = state["max_items"]
    sess = site.get("session_file")
    creds = credentials.get_creds(site["id"])
    need_login = not (sess and os.path.exists(sess))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False if need_login else True,
                                     args=["--disable-blink-features=AutomationControlled"])
        ctx_opts = {"viewport": {"width": 1280, "height": 820}, "locale": "zh-CN"}
        if sess and os.path.exists(sess):
            ctx_opts["storage_state"] = sess
        ctx = browser.new_context(**ctx_opts)
        pg = ctx.new_page()
        try:
            pg.goto(site["url"], timeout=60000)
        except Exception as e:
            state["message"] = "打开站点失败：" + str(e)
            pg.wait_for_timeout(2000)

        # ---- 登录环节 ----
        if need_login:
            has_login_form = _has_login_form(pg)
            auto = False
            if has_login_form and creds and creds.get("username") and creds.get("password"):
                auto = _try_auto_login(pg, creds)
                if auto:
                    state["message"] = "已尝试自动登录，请确认登录状态"
            if has_login_form:
                for i in range(18):
                    if state["status"] == "cancelled":
                        return
                    pg.wait_for_timeout(5000)
                    state["message"] = "请在打开的浏览器中完成登录（{}秒后自动保存并开始）".format(max(90 - (i + 1) * 5, 0))
                    if auto and not _still_login(pg):
                        break
            else:
                state["message"] = "检测到无需登录，直接开始…"
            session.save_session_state(ctx, site)

        # ---- 搜索环节 ----
        if keyword:
            if _do_search(pg, keyword):
                state["message"] = "正在检索『{}』…".format(keyword)
                pg.wait_for_timeout(4000)
            else:
                state["message"] = "未能自动定位搜索框，请在浏览器中手动搜索（30秒后开始抓取）"
                for i in range(6):
                    if state["status"] == "cancelled":
                        return
                    pg.wait_for_timeout(5000)
        else:
            state["message"] = "未输入关键词，将抓取当前页面内容"

        # ---- 翻页抓取 ----
        seen_urls = set()
        found = []
        for page_no in range(1, pages + 1):
            if state["status"] == "cancelled":
                return
            if len(found) >= max_items:
                break
            state["page"] = page_no
            state["message"] = "正在抓取第 {} 页…".format(page_no)
            items = extract_list(pg)
            new_items = [it for it in items if it["url"] not in seen_urls]
            for it in new_items:
                seen_urls.add(it["url"])
            # 抓详情正文
            for it in new_items:
                if state["status"] == "cancelled":
                    return
                if len(found) >= max_items:
                    break
                rec = {
                    "title": it["title"],
                    "url": it["url"],
                    "site_id": site["id"],
                    "site_name": site["name"],
                    "content": "",
                    "summary": "",
                    "year": _year_of(it["title"]),
                    "keywords": [],
                }
                if depth > 0:
                    state["message"] = "正在抓取详情：{}".format(it["title"][:30])
                    info = _extract_detail(browser, ctx, pg, it["url"])
                    if info["content"]:
                        rec["title"] = info["title"] or it["title"]
                        rec["content"] = info["content"]
                        rec["summary"] = info["content"][:300]
                        rec["year"] = _year_of(info["content"] + info["title"]) or rec["year"]
                if rec["title"]:
                    found.append(rec)
            state["records"] = found
            state["found"] = len(found)
            if len(found) >= max_items:
                break
            nxt = _find_next(pg)
            if not nxt:
                state["message"] = "第 {} 页无更多翻页，结束".format(page_no)
                break
            try:
                nxt.click()
                pg.wait_for_timeout(2500)
            except Exception:
                break
            time.sleep(1)
        state["status"] = "done"
        state["message"] = "完成，共抓取 {} 条".format(len(found))
        browser.close()


def _try_auto_login(pg, creds):
    from .login import _auto_fill_login
    return _auto_fill_login(pg, creds.get("username", ""), creds.get("password", ""))


def _still_login(pg):
    try:
        return bool(pg.query_selector("input[type=password]"))
    except Exception:
        return True


def _has_login_form(pg):
    try:
        return bool(pg.query_selector("input[type=password]"))
    except Exception:
        return True
