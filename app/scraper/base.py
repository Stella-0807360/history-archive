import threading
import time

JOBS = {}
LOGIN_JOBS = {}

LOCK = threading.Lock()


def _init_state(job_id, kind, **kw):
    state = {
        "status": "running",
        "kind": kind,
        "message": "启动中",
        "error": "",
        "found": 0,
        "records": [],
        "started": int(time.time() * 1000),
    }
    state.update(kw)
    return state


def start_job(worker, worker_args, store, state):
    t = threading.Thread(target=_wrap_worker, args=(worker, worker_args, store, state), daemon=True)
    t.start()
    return {"ok": True, "status": "running"}


def _wrap_worker(worker, args, store, state):
    try:
        worker(*args, state)
    except Exception as e:
        state["status"] = "error"
        state["error"] = str(e)
        state["message"] = "出错：" + str(e)
    finally:
        if state["status"] == "running":
            state["status"] = "done"
            state["message"] = state["message"] or "完成"


def cancel(store, key):
    with LOCK:
        s = store.get(key)
        if s:
            s["status"] = "cancelled"
    return {"ok": True}


def status_of(store, key):
    s = store.get(key)
    if not s:
        return {"status": "idle"}
    out = dict(s)
    out.pop("records", None)
    return out


def preview_of(store, key):
    s = store.get(key)
    return (s["records"] if s else [])
