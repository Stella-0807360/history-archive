/* ============ 历史资料智能抓取平台 · 前端 ============ */
var API = {
  q: function(path, opts) {
    var p = (opts && opts.params) ? '?' + URLSP(opts.params) : '';
    var o = { method: (opts && opts.method) || 'GET', headers: {} };
    var at = localStorage.getItem('at');
    if (at) o.headers['X-Auth-Token'] = at;
    if (opts && opts.body) {
      o.headers['Content-Type'] = 'application/json';
      o.body = JSON.stringify(opts.body);
    }
    return fetch('/api' + path + p, o).then(function(r) {
      return r.json().then(function(j) { return { status: r.status, body: j }; });
    });
  },
  blob: function(path, opts) {
    var p = (opts && opts.params) ? '?' + URLSP(opts.params) : '';
    var o = { method: (opts && opts.method) || 'GET', headers: {} };
    var at = localStorage.getItem('at');
    if (at) o.headers['X-Auth-Token'] = at;
    return fetch('/api' + path + p, o).then(function(r) {
      if (!r.ok) throw new Error('请求失败');
      return r.blob();
    });
  }
};
function URLSP(obj) {
  var parts = [];
  for (var k in obj) if (obj[k] !== '' && obj[k] !== null && obj[k] !== undefined) parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(obj[k]));
  return parts.join('&');
}
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function fmtDate(ms) { if (!ms) return ''; var d = new Date(ms); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
function download(name, blob) { var u = URL.createObjectURL(blob); var a = document.createElement('a'); a.href = u; a.download = name; document.body.appendChild(a); a.click(); setTimeout(function(){ URL.revokeObjectURL(u); a.remove(); }, 300); }
function toast(msg) { var t = document.getElementById('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._tm); t._tm = setTimeout(function(){ t.classList.remove('show'); }, 2400); }

/* ---------- 弹窗 ---------- */
var Modal = {
  open: function(title, html, foot) {
    var root = document.getElementById('modal-root');
    root.innerHTML = '<div class="mask" onclick="if(event.target===this)Modal.close()">' +
      '<div class="box"><h3>' + esc(title) + '</h3><div>' + html + '</div>' +
      '<div class="row mt" style="justify-content:flex-end">' + (foot || '<button class="btn" onclick="Modal.close()">关闭</button>') + '</div></div></div>';
  },
  close: function() { document.getElementById('modal-root').innerHTML = ''; }
};

/* ---------- 认证 ---------- */
var Auth = {
  mode: null,
  check: function() {
    API.q('/auth/status').then(function(r) {
      var has = !!(r.body && r.body.has_password);
      Auth.mode = has ? 'login' : 'setup';
      if (has && localStorage.getItem('at')) {
        API.q('/sites').then(function(r2) {
          if (r2.status === 401) { localStorage.removeItem('at'); Auth.show(); }
          else { Auth.hide(); App.go('crawl'); }
        });
      } else Auth.show();
    });
  },
  show: function() {
    document.getElementById('topbar').classList.add('hidden');
    document.getElementById('page-login').classList.remove('hidden');
    var isSetup = Auth.mode === 'setup';
    document.getElementById('login-title').textContent = isSetup ? '设置访问口令' : '输入访问口令';
    document.getElementById('login-sub').textContent = isSetup ? '首次使用，请设置访问口令（公网访问必备，可跳过）' : '本平台数据仅供个人学术研究使用';
    document.getElementById('pw-btn').textContent = isSetup ? '保存并进入' : '进入平台';
    document.getElementById('pw-skip').classList.toggle('hidden', !isSetup);
    document.getElementById('pw-msg').textContent = '';
  },
  submit: function() {
    var pw = document.getElementById('pw-input').value;
    if (!pw) { document.getElementById('pw-msg').textContent = '请输入口令'; return; }
    var isSetup = Auth.mode === 'setup';
    API.q(isSetup ? '/auth/setup' : '/auth/login', { method: 'POST', body: { password: pw, old_password: pw, new_password: pw } })
      .then(function(r) {
        if (r.body && r.body.ok && r.body.token) {
          localStorage.setItem('at', r.body.token);
          document.getElementById('pw-input').value = '';
          toast('欢迎进入');
          Auth.hide();
          App.go('crawl');
        } else document.getElementById('pw-msg').textContent = r.body.msg || '失败';
      });
  },
  skip: function() {
    localStorage.setItem('at', '');
    Auth.hide(); App.go('crawl');
  },
  hide: function() {
    document.getElementById('page-login').classList.add('hidden');
    document.getElementById('topbar').classList.remove('hidden');
  }
};

/* ---------- 视图切换 ---------- */
var S = { page: 'crawl', sites: [], site: '', kw: '', pages: 3, depth: 1, max: 50, lib: {}, crawlTimer: null, loginTimer: null };
var App = {
  go: function(page) {
    S.page = page;
    document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.toggle('on', n.dataset.page === page); });
    window.scrollTo(0, 0);
    if (page === 'crawl') renderCrawl();
    else if (page === 'library') renderLibrary();
    else if (page === 'settings') renderSettings();
  }
};

/* ============================================================
   抓取页
============================================================ */
function renderCrawl() {
  var v = document.getElementById('view');
  v.innerHTML =
    '<div class="card"><h3>站点管理</h3>' +
      '<div class="row">' +
        '<input type="text" id="s-name" placeholder="站点名称（如：抗战文献数据平台）" style="flex:1;min-width:160px">' +
        '<input type="url" id="s-url" placeholder="网址，如 https://www.example.com" style="flex:1.6;min-width:200px">' +
        '<button class="btn btn-primary" onclick="Crawl.addSite()">添加</button>' +
      '</div>' +
      '<div id="site-list" class="mt">加载中…</div>' +
    '</div>' +
    '<div class="card"><h3>抓取参数</h3>' +
      '<label class="lb">选择站点</label><select id="c-site"></select>' +
      '<label class="lb">账号密码（可选，自动登录用，将加密保存）</label>' +
      '<div class="row"><input type="text" id="c-user" placeholder="账号" style="flex:1"><input type="password" id="c-pw" placeholder="密码" style="flex:1">' +
      '<button class="btn btn-sm" onclick="Crawl.saveCreds()">保存凭据</button>' +
      '<button class="btn btn-sm btn-gold" onclick="Crawl.openLogin()">打开浏览器登录</button>' +
      '<span class="badge" id="login-badge"></span></div>' +
      '<label class="lb">关键词</label><input type="text" id="c-kw" placeholder="要搜索的内容关键词">' +
      '<div class="row mt">' +
        '<label class="lb" style="margin:0">页数</label><input class="short" type="number" id="c-pages" value="3" min="1" max="30">' +
        '<label class="lb" style="margin:0">抓正文</label><select id="c-depth" class="short" style="width:110px"><option value="1" selected>抓详情正文</option><option value="0">仅列表</option></select>' +
        '<label class="lb" style="margin:0">上限</label><input class="short" type="number" id="c-max" value="50" min="5" max="500">' +
        '<button class="btn btn-primary" id="c-run" onclick="Crawl.run()">开始抓取</button>' +
        '<button class="btn" id="c-stop" onclick="Crawl.cancel()" style="display:none">停止</button>' +
      '</div>' +
      '<div class="muted mt" id="c-msg"></div><div class="progress hidden" id="c-prog"><i id="c-prog-i"></i></div>' +
    '</div>' +
    '<div class="card"><h3>抓取结果预览</h3><div id="c-preview" class="muted">尚未抓取</div></div>' +
    '<div class="card"><h3>关联词分析</h3>' +
      '<div class="row"><button class="btn btn-primary" id="c-an" onclick="Crawl.analyze()">生成关联词</button>' +
      '<span class="muted">基于本次抓取正文，统计与关键词共现的高频词</span></div>' +
      '<div class="muted mt" id="c-anmsg"></div>' +
      '<div class="cloud-wrap hidden mt" id="c-cloud"><canvas id="c-cloud-canvas"></canvas></div>' +
      '<div class="kw-list" id="c-kwlist"></div>' +
    '</div>';
  Crawl.refresh();
}

var Crawl = {
  loadSites: function(cb) {
    API.q('/sites').then(function(r) {
      if (r.status === 401) { localStorage.removeItem('at'); Auth.check(); return; }
      S.sites = r.body.sites || [];
      Crawl.drawSites();
      Crawl.drawSiteSelect();
      if (cb) cb();
    });
  },
  refresh: function() {
    Crawl.loadSites(function() { Crawl.pollStatus(); });
  },
  drawSites: function() {
    var el = document.getElementById('site-list');
    if (!el) return;
    var list = S.sites;
    if (!list.length) { el.innerHTML = '<div class="muted">暂无站点，请在上方添加</div>'; return; }
    el.innerHTML = list.map(function(s) {
      var lg = s.login || {}, cr = s.crawl || {};
      var credTag = s.has_creds ? '<span class="tag tag-gold">已存凭据</span>' : '';
      var sessTag = s.has_session ? '<span class="tag tag-cinnabar">有会话</span>' : '';
      return '<div class="site-row">' +
        '<div class="row"><span class="t">' + esc(s.name) + '</span>' +
          '<span class="badge ' + (cr.status === 'running' ? 'run' : (cr.status === 'done' ? 'done' : (cr.status === 'error' ? 'error' : ''))) + '" id="cr-' + s.id + '">' + esc(cr.status) + '</span>' + credTag + sessTag +
          '<span style="margin-left:auto"><button class="btn btn-sm" onclick="Crawl.select(\'' + s.id + '\')">选择</button>' +
          '<button class="btn btn-sm btn-danger" onclick="Crawl.delSite(\'' + s.id + '\')">删除</button></span></div>' +
        '<div class="d">' + esc(s.url) + '</div>' +
        (s.note ? '<div class="d">' + esc(s.note) + '</div>' : '') +
        '<div class="muted" id="cm-' + s.id + '">' + (cr.message || '') + '</div>' +
      '</div>';
    }).join('');
  },
  drawSiteSelect: function() {
    var el = document.getElementById('c-site');
    if (!el) return;
    var list = S.sites;
    if (!list.length) { el.innerHTML = '<option value="">请先添加站点</option>'; return; }
    el.innerHTML = list.map(function(s) {
      return '<option value="' + s.id + '"' + (s.id === S.site ? ' selected' : '') + '>' + esc(s.name) + '</option>';
    }).join('');
    if (S.site && list.some(function(s){ return s.id === S.site; })) {
      var cur = list.filter(function(s){ return s.id === S.site; })[0];
      var ub = document.getElementById('login-badge');
      if (ub) {
        ub.textContent = cur.has_creds ? '已存凭据' : (cur.has_session ? '有会话' : '未登录');
        ub.className = 'badge ' + (cur.has_creds || cur.has_session ? 'done' : '');
      }
    }
  },
  select: function(id) {
    S.site = id;
    Crawl.drawSiteSelect();
    toast('已选择站点');
  },
  addSite: function() {
    var name = document.getElementById('s-name').value.trim();
    var url = document.getElementById('s-url').value.trim();
    if (!name || !url) { toast('请填写名称与网址'); return; }
    API.q('/sites', { method: 'POST', body: { name: name, url: url } }).then(function(r) {
      if (r.body.ok) { toast('站点已添加'); document.getElementById('s-name').value = ''; document.getElementById('s-url').value = ''; Crawl.refresh(); }
      else toast(r.body.detail || '失败');
    });
  },
  delSite: function(id) {
    if (!confirm('删除该站点及其会话？（不影响已入库资料）')) return;
    API.q('/sites/' + id, { method: 'DELETE' }).then(function() { if (S.site === id) S.site = ''; Crawl.refresh(); });
  },
  saveCreds: function() {
    var id = document.getElementById('c-site').value;
    if (!id) { toast('请先选择站点'); return; }
    var u = document.getElementById('c-user').value;
    var p = document.getElementById('c-pw').value;
    API.q('/sites/' + id, { method: 'PUT', body: { username: u, password: p } }).then(function() {
      toast('凭据已加密保存'); Crawl.refresh();
    });
  },
  openLogin: function() {
    var id = document.getElementById('c-site').value;
    if (!id) { toast('请先选择站点'); return; }
    toast('将在电脑屏幕打开浏览器，请在弹出窗口中完成登录');
    API.q('/crawl/login', { method: 'POST', body: { site_id: id } }).then(function(r) {
      if (r.body.ok) Crawl.pollLogin(id); else toast(r.body.msg || '启动失败');
    });
  },
  pollLogin: function(id) {
    if (S.loginTimer) clearInterval(S.loginTimer);
    S.loginTimer = setInterval(function() {
      API.q('/crawl/login/status', { params: { site_id: id } }).then(function(r) {
        var st = r.body;
        if (st.status === 'done') { clearInterval(S.loginTimer); toast('登录会话已保存'); Crawl.refresh(); }
        else if (st.status === 'error') { clearInterval(S.loginTimer); toast(st.message || '登录出错'); Crawl.refresh(); }
        else {
          var b = document.getElementById('login-badge');
          if (b) { b.textContent = st.message || st.status; b.className = 'badge run'; }
        }
      });
    }, 2000);
  },
  run: function() {
    var id = document.getElementById('c-site').value;
    if (!id) { toast('请先选择站点'); return; }
    var kw = document.getElementById('c-kw').value.trim();
    var pages = parseInt(document.getElementById('c-pages').value || '3', 10);
    var depth = parseInt(document.getElementById('c-depth').value || '1', 10);
    var max = parseInt(document.getElementById('c-max').value || '50', 10);
    S.site = id;
    API.q('/crawl/run', { method: 'POST', body: { site_id: id, keyword: kw, pages: pages, depth: depth, max_items: max } })
      .then(function(r) {
        if (r.body.ok) { toast('抓取已启动'); document.getElementById('c-run').style.display = 'none'; document.getElementById('c-stop').style.display = ''; Crawl.pollStatus(); }
        else toast(r.body.msg || '启动失败');
      });
  },
  cancel: function() {
    var id = document.getElementById('c-site').value;
    API.q('/crawl/cancel', { method: 'POST', body: { site_id: id } }).then(function() { toast('已停止'); });
  },
  pollStatus: function() {
    if (S.crawlTimer) clearTimeout(S.crawlTimer);
    var tick = function() {
      if (!S.site) { S._wasRunning = false; return; }
      API.q('/crawl/status', { params: { site_id: S.site } }).then(function(r) {
        var st = r.body;
        var b = document.getElementById('cr-' + S.site);
        var m = document.getElementById('cm-' + S.site);
        var msg = document.getElementById('c-msg');
        var prog = document.getElementById('c-prog');
        var runBtn = document.getElementById('c-run');
        var stopBtn = document.getElementById('c-stop');
        if (b) { b.textContent = st.status; b.className = 'badge ' + (st.status === 'running' ? 'run' : (st.status === 'done' ? 'done' : (st.status === 'error' ? 'error' : ''))); }
        if (m && st.message) m.textContent = st.message + '（已抓取 ' + (st.found || 0) + ' 条）';
        if (msg) msg.textContent = st.message || '';
        if (prog) {
          if (st.status === 'running') { prog.classList.remove('hidden'); prog.querySelector('i').style.width = Math.min(100, Math.round((st.page || 0) / Math.max(1, st.pages) * 100)) + '%'; }
          else prog.classList.add('hidden');
        }
        if (runBtn && stopBtn) {
          if (st.status === 'running') { runBtn.style.display = 'none'; stopBtn.style.display = ''; }
          else { runBtn.style.display = ''; stopBtn.style.display = 'none'; }
        }
        if (st.status === 'running') {
          S._wasRunning = true;
          S.crawlTimer = setTimeout(tick, 2000);
        } else {
          var was = S._wasRunning;
          S._wasRunning = false;
          if (st.status === 'done' || st.status === 'error') { Crawl.preview(); if (was) Crawl.loadSites(); }
        }
      });
    };
    tick();
  },
  preview: function() {
    API.q('/crawl/preview', { params: { site_id: S.site } }).then(function(r) {
      var el = document.getElementById('c-preview');
      if (!el) return;
      var recs = r.body.records || [];
      if (!recs.length) { el.innerHTML = '<span class="muted">尚未抓取</span>'; return; }
      var h = '<div class="row"><span>共 <b>' + r.body.total + '</b> 条</span>' +
        '<button class="btn btn-sm btn-primary" onclick="Crawl.doImport()">全部入库 (' + r.body.total + ')</button>' +
        '<button class="btn btn-sm" onclick="Crawl.previewDetail()">查看列表</button></div>';
      el.innerHTML = h;
    });
  },
  previewDetail: function() {
    API.q('/crawl/preview', { params: { site_id: S.site } }).then(function(r) {
      var recs = r.body.records || [];
      var rows = recs.map(function(x, i) {
        return '<div class="res"><div class="rt" onclick="window.open(\'' + esc(x.url) + '\')">' + (i + 1) + '. ' + esc(x.title) + '</div>' +
          '<div class="rm">' + esc(x.url) + '</div>' +
          (x.content ? '<div class="rs">' + esc(x.content).substring(0, 160) + '…</div>' : '') + '</div>';
      }).join('');
      Modal.open('抓取预览（' + recs.length + ' 条）', rows, '<button class="btn" onclick="Modal.close()">关闭</button>');
    });
  },
  doImport: function() {
    API.q('/crawl/import', { method: 'POST', body: { site_id: S.site } }).then(function(r) {
      if (r.body.ok) { toast('已入库：新增 ' + r.body.report.added + '，重复 ' + r.body.report.dup); Crawl.refresh(); }
      else toast(r.body.detail || '导入失败');
    });
  },
  analyze: function() {
    var id = document.getElementById('c-site').value;
    var kw = document.getElementById('c-kw').value.trim();
    var msg = document.getElementById('c-anmsg');
    msg.textContent = '分析中…（首次加载中文分词库会稍慢）';
    API.q('/crawl/analyze', { method: 'POST', body: { site_id: id, keyword: kw } }).then(function(r) {
      if (r.status === 400) { msg.textContent = r.body.detail; return; }
      msg.textContent = '';
      var cloud = r.body.cloud || [];
      document.getElementById('c-cloud').classList.remove('hidden');
      drawWordCloud(document.getElementById('c-cloud-canvas'), cloud);
      var list = document.getElementById('c-kwlist');
      var maxS = cloud.length ? cloud[0].weight : 1;
      list.innerHTML = cloud.map(function(w, i) {
        var cls = w.weight > maxS * 0.7 ? 'hi' : (w.weight > maxS * 0.4 ? 'mid' : 'lo');
        var wpercent = Math.round(w.weight / maxS * 100);
        return '<div class="kw-item ' + cls + '" onclick="Crawl.goSearch(\'' + esc(w.word) + '\')">' +
          '<span class="rank">' + (i + 1) + '</span><span class="word">' + esc(w.word) + '</span>' +
          '<span class="bar"><i style="width:' + wpercent + '%"></i></span>' +
          '<span class="cnt">' + w.count + '</span></div>';
      }).join('');
      toast('已生成 ' + cloud.length + ' 个关联词');
    });
  },
  goSearch: function(w) {
    S.lib = { term: w };
    App.go('library');
    document.getElementById('l-term').value = w;
    Lib.search(1);
  }
};

/* ============================================================
   资料库
============================================================ */
function renderLibrary() {
  var v = document.getElementById('view');
  v.innerHTML =
    '<div class="card"><h3>资料库检索</h3>' +
      '<div class="row">' +
        '<input type="text" id="l-term" placeholder="输入关键词检索全文（如：统一战线、抗战、南京）" value="' + esc(S.lib.term || '') + '" style="flex:1.8">' +
        '<button class="btn btn-primary" onclick="Lib.search(1)">检索</button>' +
      '</div>' +
      '<div class="row mt">' +
        '<select id="l-site" style="max-width:200px"><option value="">全部站点</option></select>' +
        '<span class="muted" id="l-info"></span>' +
        '<span style="margin-left:auto"><button class="btn btn-sm" onclick="Lib.exportCurrent()">导出全部结果</button></span>' +
      '</div>' +
    '</div>' +
    '<div id="l-results"><div class="empty">输入关键词开始检索</div></div>' +
    '<div id="l-pager" class="row mt" style="justify-content:center"></div>';
  API.q('/sites').then(function(r) {
    var sel = document.getElementById('l-site');
    if (sel) sel.innerHTML = '<option value="">全部站点</option>' + (r.body.sites || []).map(function(s) { return '<option value="' + s.id + '">' + esc(s.name) + '</option>'; }).join('');
  });
  if (S.lib.term) Lib.search(1);
}

var Lib = {
  search: function(page) {
    S.lib.page = page || 1;
    S.lib.term = document.getElementById('l-term').value.trim();
    S.lib.site = document.getElementById('l-site').value;
    var params = { term: S.lib.term, site_id: S.lib.site, page: S.lib.page, size: 15, sort: 'year' };
    API.q('/records', { params: params }).then(function(r) {
      if (r.status === 401) { localStorage.removeItem('at'); Auth.check(); return; }
      var j = r.body;
      document.getElementById('l-info').textContent = '共 ' + j.total + ' 条';
      var el = document.getElementById('l-results');
      if (!j.items.length) { el.innerHTML = '<div class="empty">没有匹配记录，可到「抓取」页采集</div>'; document.getElementById('l-pager').innerHTML = ''; return; }
      el.innerHTML = j.items.map(function(x) {
        var meta = [];
        if (x.site_name) meta.push(esc(x.site_name));
        if (x.year) meta.push(x.year + ' 年');
        if (x.url) meta.push('网页');
        var kws = (x.keywords || []).slice(0, 4).map(function(k) { return '<span class="tag">' + esc(k) + '</span>'; }).join('');
        return '<div class="res"><div class="rt" onclick="Lib.detail(\'' + x.id + '\')">' + esc(x.title) + '</div>' +
          '<div class="rm">' + meta.join(' · ') + '</div>' +
          (x.summary ? '<div class="rs">' + esc(x.summary).substring(0, 140) + (x.summary.length > 140 ? '…' : '') + '</div>' : '') +
          '<div class="row mt">' + kws +
            '<span style="margin-left:auto"><button class="btn btn-sm" onclick="Lib.exportOne(\'' + x.id + '\')">导出</button>' +
            '<button class="btn btn-sm btn-danger" onclick="Lib.del(\'' + x.id + '\')">删除</button></span></div></div>';
      }).join('');
      var pages = Math.max(1, Math.ceil(j.total / 15));
      var pager = '';
      if (pages > 1) {
        var start = Math.max(1, Math.min(S.lib.page - 3, pages - 6));
        for (var i = start; i <= Math.min(pages, start + 6); i++) {
          pager += '<button class="btn btn-sm' + (i === S.lib.page ? ' btn-gold' : '') + '" onclick="Lib.search(' + i + ')">' + i + '</button> ';
        }
      }
      document.getElementById('l-pager').innerHTML = pager;
    });
  },
  detail: function(id) {
    API.q('/records/' + id).then(function(r) {
      var x = r.body;
      Modal.open(x.title,
        '<div class="muted">' + esc(x.site_name) + (x.year ? ' · ' + x.year + ' 年' : '') + '</div>' +
        '<div class="row mt"><a class="link" href="' + esc(x.url) + '" target="_blank">打开原文 ↗</a></div>' +
        '<div class="sep">正文</div>' +
        '<div style="white-space:pre-wrap;font-family:SimSun,serif;font-size:14px;line-height:1.9;max-height:52vh;overflow:auto">' + esc(x.content || x.summary || '（无正文）') + '</div>' +
        '<div class="sep">关键词</div><div>' + (x.keywords || []).map(function(k){ return '<span class="tag tag-gold">' + esc(k) + '</span>'; }).join('') + '</div>',
        '<button class="btn" onclick="Modal.close()">关闭</button>' +
        '<button class="btn btn-primary" onclick="Lib.exportOne(\'' + x.id + '\')">导出此条</button>');
    });
  },
  exportOne: function(id) {
    Modal.pickFmt(function(fmt) {
      API.blob('/export', { params: { ids: id, fmt: fmt } }).then(function(b) { download(ExportName(fmt), b); });
    });
  },
  exportCurrent: function() {
    var self = this;
    API.q('/records', { params: { term: S.lib.term || '', site_id: S.lib.site || '', page: 1, size: 500, sort: 'year' } }).then(function(r) {
      var ids = (r.body.items || []).map(function(x) { return x.id; });
      if (!ids.length) { toast('无结果可导出'); return; }
      Modal.pickFmt(function(fmt) {
        API.blob('/export', { params: { ids: ids.join(','), fmt: fmt } }).then(function(b) { download(ExportName(fmt), b); });
      });
    });
  },
  del: function(id) {
    if (!confirm('删除该条资料？')) return;
    API.q('/records/' + id, { method: 'DELETE' }).then(function() { Lib.search(S.lib.page || 1); });
  }
};

/* 导出格式选择 */
Modal.pickFmt = function(cb) {
  var fmts = [['txt', '纯文本 (题录+摘要)'], ['gbt', 'GB/T 7714 参考文献'], ['csv', 'CSV 表格'], ['json', 'JSON 全文']];
  window._pf = function(fmt) { cb(fmt); };
  var html = fmts.map(function(f) { return '<button class="btn btn-sm" style="width:100%" onclick="Modal.close();_pf(\'' + f[0] + '\')">' + f[1] + '</button>'; }).join('<div style="height:6px"></div>');
  Modal.open('选择导出格式', html, '');
};
function ExportName(fmt) {
  return { txt: '抓取资料.txt', gbt: '抓取资料_GB7714.txt', csv: '抓取资料.csv', json: '抓取资料.json' }[fmt] || '抓取资料.txt';
}

/* ============================================================
   设置
============================================================ */
function renderSettings() {
  var v = document.getElementById('view');
  var cur = location.origin + location.pathname;
  v.innerHTML =
    '<div class="card"><h3>公网访问</h3>' +
      '<div class="muted">当前地址（手机扫码即可打开）：</div>' +
      '<div class="row mt"><code style="background:#f6efdd;padding:6px 10px;border-radius:4px;word-break:break-all">' + esc(cur) + '</code></div>' +
      '<div class="row mt"><img id="qr-img" style="width:150px;height:150px;background:#fff;border:1px solid var(--card-line);border-radius:4px" alt="二维码">' +
      '<div class="muted" style="flex:1">手机与本功能同时访问公网链接即可使用。<br>公网访问方式：使用 cpolar / ngrok / 路由器端口映射 将 8000 端口映射出去。</div></div>' +
    '</div>' +
    '<div class="card"><h3>访问口令</h3><div id="pw-box">…</div></div>' +
    '<div class="card"><h3>数据管理</h3>' +
      '<div class="row">' +
        '<button class="btn" onclick="Set.backup()">导出全部数据 (JSON)</button>' +
        '<button class="btn btn-danger" onclick="Set.clear()">清空资料库</button>' +
      '</div>' +
      '<div class="muted mt">数据保存在项目 data 目录（SQLite + 会话文件）。导出 JSON 含全部正文。</div>' +
    '</div>' +
    '<div class="card"><h3>关于</h3>' +
      '<div class="muted">历史资料智能抓取平台 v1.0 · 本工具仅用于个人学术研究与资料整理。抓取内容请遵守目标网站使用条款与版权规定。</div>' +
    '</div>';
  API.blob('/qr', { params: { text: cur } }).then(function(b) {
    var img = document.getElementById('qr-img');
    if (img) img.src = URL.createObjectURL(b);
  });
  Set.pwBox();
}

var Set = {
  pwBox: function() {
    API.q('/auth/status').then(function(r) {
      var has = r.body.has_password;
      var el = document.getElementById('pw-box');
      if (!el) return;
      if (!has) {
        el.innerHTML = '<label class="lb">尚未设置口令，公网访问请务必设置</label>' +
          '<div class="row"><input type="password" id="np1" placeholder="新口令（至少4位）" style="max-width:220px">' +
          '<button class="btn btn-primary" onclick="Set.setPw()">设置</button></div>';
      } else {
        el.innerHTML = '<label class="lb">修改口令</label>' +
          '<div class="row"><input type="password" id="op" placeholder="原口令" style="max-width:180px">' +
          '<input type="password" id="np1" placeholder="新口令" style="max-width:180px">' +
          '<button class="btn" onclick="Set.chgPw()">修改</button></div>';
      }
    });
  },
  setPw: function() {
    var pw = document.getElementById('np1').value;
    if (pw.length < 4) { toast('口令至少 4 位'); return; }
    API.q('/auth/setup', { method: 'POST', body: { password: pw } }).then(function(r) {
      if (r.body.ok && r.body.token) { localStorage.setItem('at', r.body.token); toast('口令已设置'); Set.pwBox(); }
      else toast(r.body.msg || '失败');
    });
  },
  chgPw: function() {
    var op = document.getElementById('op').value;
    var np = document.getElementById('np1').value;
    API.q('/auth/change', { method: 'POST', body: { old_password: op, new_password: np } }).then(function(r) {
      if (r.body.ok && r.body.token) { localStorage.setItem('at', r.body.token); toast('口令已修改'); Set.pwBox(); }
      else toast(r.body.msg || '失败');
    });
  },
  backup: function() {
    API.blob('/export', { params: { fmt: 'json' } }).then(function(b) { download('抓取资料备份_' + fmtDate(Date.now()) + '.json', b); });
  },
  clear: function() {
    if (!confirm('确定清空全部资料库？不可恢复！')) return;
    API.q('/records', { method: 'DELETE' }).then(function() { toast('已清空'); });
  }
};

/* ============================================================
   词云渲染（纯 Canvas，无外部依赖）
============================================================ */
function drawWordCloud(canvas, words) {
  if (!canvas || !words || !words.length) return;
  var W = canvas.clientWidth || 600;
  var H = canvas.clientHeight || 320;
  var dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  var maxW = words[0].weight || 1;
  var placed = [];
  var font = '"Songti SC","STSong","SimSun",serif';
  words.forEach(function(w) {
    var size = w.size || 24;
    ctx.font = size + 'px ' + font;
    var tw = ctx.measureText(w.word).width + size * 0.5;
    var th = size * 1.25;
    var x = W / 2, y = H / 2, ok = false;
    for (var k = 0; k < 1600; k++) {
      var r = (k / 1600) * Math.max(W, H) * 0.55;
      var a = k * 0.42 + w.word.length;
      x = W / 2 + Math.cos(a) * r;
      y = H / 2 + Math.sin(a) * r;
      if (x - tw / 2 < 0 || x + tw / 2 > W || y - th / 2 < 0 || y + th / 2 > H) continue;
      if (!hit(placed, x, y, tw, th)) { ok = true; break; }
    }
    if (!ok) {
      for (var j = 0; j < 400 && !ok; j++) {
        x = tw / 2 + Math.random() * (W - tw);
        y = th / 2 + Math.random() * (H - th);
        if (!hit(placed, x, y, tw, th)) ok = true;
      }
    }
    placed.push({ x: x, y: y, w: tw, h: th });
    var ratio = w.weight / maxW;
    ctx.fillStyle = ratio > 0.72 ? '#A63D2F' : (ratio > 0.4 ? '#5C4B36' : '#B08D3E');
    ctx.font = size + 'px ' + font;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(w.word, x, y);
  });
}
function hit(placed, x, y, tw, th) {
  for (var i = 0; i < placed.length; i++) {
    var p = placed[i];
    if (x + tw / 2 > p.x - p.w / 2 && x - tw / 2 < p.x + p.w / 2 && y + th / 2 > p.y - p.h / 2 && y - th / 2 < p.y + p.h / 2) return true;
  }
  return false;
}

/* ============================================================
   启动
============================================================ */
window.onload = function() {
  var q = (location.hash.match(/q=([^&]*)/) || [])[1];
  if (q) { S.lib.term = decodeURIComponent(q); location.hash = ''; }
  Auth.check();
};
