import os
import re

import jieba
import jieba.analyse
import jieba.posseg

from . import db

KEEP_TAGS = ("n", "ng", "nr", "nr1", "nr2", "ns", "nt", "nz", "vn", "an", "j", "f")
MIN_WORD = 2

DEFAULT_STOP = set("""的 了 和 是 在 与 及 或 也 都 而 又 被 把 这 那 之 其 我 你 他 她 它 我们 你们 他们
有 一个 一些 没有 进行 可以 这样 那样 这个 那个 这些 那些 因为 所以 但是 不过 而且 并且 或者
以及 对于 关于 通过 根据 按照 主要 其中 以及 更加 已经 将会 可能 应该 需要 由于 于是 因此 然而
从 到 上 下 中 内 外 前 后 间 时 里 地 得 所 于 将 让 给 向 以 为 若 如 则 即 使 比 每 各 该
什么 怎么 怎样 如何 为什么 时候 地方 方式 方面 情况 问题 内容 部分 全部 还有 包括 就是 只是
article 摘要 关键词 全文 网页 本文 内容 作者 日期 时间 下载 阅读 查看 搜索 检索 相关 更多""".split())


def _stopwords():
    words = set(DEFAULT_STOP)
    if os.path.exists(db.STOPWORDS_PATH):
        with open(db.STOPWORDS_PATH, encoding="utf-8") as f:
            words.update(line.strip() for line in f if line.strip() and not line.startswith("#"))
    return words


def _seg(text):
    return [(w.word, w.flag) for w in jieba.posseg.cut(text or "")]


def extract_record_keywords(text, top_n=8):
    """单条记录的抽取式关键词（用于入库的 keywords 字段）。"""
    if not text:
        return []
    stop = _stopwords()
    tags = jieba.analyse.extract_tags(text, topK=top_n * 2)
    out = []
    for t in tags:
        if len(t) >= MIN_WORD and t not in stop and t not in out:
            out.append(t)
        if len(out) >= top_n:
            break
    return out


def analyze(keyword, records, top_n=60):
    """关联词分析：共现度 + 词频 + TextRank 加权排序。"""
    if not records:
        return []
    stop = _stopwords()
    kw = (keyword or "").strip()
    freq = {}
    co = {}
    doc_count = len(records)
    texts = []
    for rec in records:
        blob = "{} {}".format(rec.get("title", ""), rec.get("content", "") or rec.get("summary", ""))
        texts.append(blob)
        has_kw = bool(kw and kw in blob)
        seen_doc = set()
        for word, flag in _seg(blob):
            if len(word) < MIN_WORD or word in stop:
                continue
            if flag[:1] not in ("n", "v", "a", "j", "f"):
                continue
            if flag[:2] not in KEEP_TAGS and not (flag[:1] == "v" and flag[:2] == "vn"):
                continue
            freq[word] = freq.get(word, 0) + 1
            if has_kw and word not in seen_doc:
                seen_doc.add(word)
                co[word] = co.get(word, 0) + 1
    corpus = " ".join(texts)
    tr = {}
    try:
        for t, w in jieba.analyse.textrank(corpus, topK=top_n * 3, withWeight=True):
            tr[t] = w
    except Exception:
        pass
    max_f = max(freq.values()) if freq else 1
    max_co = max(co.values()) if co else 1
    max_tr = max(tr.values()) if tr else 1
    scores = {}
    for word, f in freq.items():
        s = 0.0
        s += 2.0 * (co.get(word, 0) / max_co)          # 与关键词共现
        s += 1.0 * (f / max_f)                          # 词频
        s += 1.5 * (tr.get(word, 0) / max_tr)           # 关键性
        s += 1.0 if (kw and word in kw) else 0.0        # 含关键词本身
        scores[word] = s
    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
    out = []
    for word, s in ranked:
        out.append({"word": word, "count": freq.get(word, 0), "score": round(s, 3)})
    return out


def word_cloud_data(words, max_px=64, min_px=16):
    """把关联词映射为词云渲染数据（词频/权重 → 字号）。"""
    if not words:
        return []
    max_s = words[0]["score"]
    min_s = words[-1]["score"] if len(words) > 1 else max_s
    span = (max_s - min_s) or 1
    out = []
    for w in words:
        r = (w["score"] - min_s) / span
        size = min_px + round(r * (max_px - min_px))
        out.append({"word": w["word"], "count": w["count"], "size": size,
                    "weight": w["score"]})
    return out
