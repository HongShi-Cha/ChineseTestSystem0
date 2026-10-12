/* ============================================================
 * 国语水平测试系统 - 前端脚本（对接 Python(FastAPI) + MySQL 后端）
 *
 * Backend calls restored: 本文件已接回真实接口，所有数据来自 /api/**，
 * 字段统一为 Python 社区的下划线命名（student_no / total_score /
 * finished_at / record_id ...）。
 *
 * 讯飞评测接入（第 8 步）：录音会在浏览器里解码重采样成 16k/16bit/单声道 PCM
 * 再上传（见 toIsePcm），后端调用讯飞 ISE 出分。
 *
 * 接口约定：统一返回 { code, message, data }
 *   code == 0    成功
 *   code == 401  未登录（自动跳登录页）
 *   code == 403  角色不符
 *   code == 410  本场考试已超时（服务端已自动交卷，考试页自动跳成绩页）
 *
 * 需要"纯前端、无后端"演示版时，把各页面里的
 *     <script src="../js/main.js"></script>
 * 换成
 *     <script src="../js/main.mock.js"></script>
 * 即可（mock 版数据全部内置，双击 HTML 就能看）。
 * ============================================================ */
(function () {
  'use strict';

  /* ===================== 0. 通用小工具 ===================== */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const byId = (id) => document.getElementById(id);

  /** 题型中文名 */
  const TYPE_NAMES = { 1: '读单字', 2: '读词语', 3: '朗读短文', 4: '命题说话' };
  const SECTION_TITLES = { 1: '一、读单音节字词', 2: '二、读多音节词语', 3: '三、朗读短文', 4: '四、命题说话' };
  const TYPE_TOTAL = { 1: 10, 2: 20, 3: 30, 4: 40 };   // 每个大题满分

  /** HTML 转义：数据塞进 innerHTML 前必须转义 */
  function esc(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function orDash(value) {
    return (value === null || value === undefined || value === '') ? '-' : value;
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /** 秒 -> 03:05 */
  function fmtClock(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    return pad2(Math.floor(seconds / 60)) + ':' + pad2(seconds % 60);
  }

  /** 秒 -> 03分05秒 */
  function fmtCn(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    return pad2(Math.floor(seconds / 60)) + '分' + pad2(seconds % 60) + '秒';
  }

  /** 分数显示：保留 1 位小数；null 显示 - */
  function fmtScore(value) {
    return (value === null || value === undefined) ? '-' : Number(value).toFixed(1);
  }

  /** 'YYYY-MM-DD HH:mm:ss' 只取日期部分 */
  function shortDate(s) { return (s || '').slice(0, 10); }

  function round1(n) { return Math.round(n * 10) / 10; }

  /** 后端返回的时间字符串 -> Date（兼容 Safari） */
  function parseDateTime(text) {
    if (!text) return null;
    const d = new Date(String(text).replace(/-/g, '/'));
    return isNaN(d.getTime()) ? null : d;
  }

  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = orDash(value);
  }

  function setHtml(id, html) {
    const node = byId(id);
    if (node) node.innerHTML = html;
  }

  /** 读 URL 参数，如 exam.html?type=2 -> queryParam('type') */
  function queryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function isInside(dir) {
    return window.location.pathname.toLowerCase().indexOf('/' + dir + '/') !== -1;
  }

  /** 登录页相对路径（学生/管理员页面在子目录里，要回上一级） */
  function loginPageUrl() {
    return (isInside('student') || isInside('admin')) ? '../login.html' : 'login.html';
  }

  /** 页面在子目录时的上一级前缀 */
  function upPrefix() {
    return (isInside('student') || isInside('admin')) ? '../' : '';
  }

  /** Date -> 'YYYY-MM-DD HH:mm:ss' */
  function fmtDateTime(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  /* ===================== 1. 等级徽章 ===================== */
  function levelBadgeClass(level) {
    if (!level) return 'text-bg-light';
    if (level.indexOf('一级') !== -1) return 'text-bg-warning';
    if (level.indexOf('二级甲') !== -1) return 'text-bg-success';
    if (level.indexOf('二级') !== -1) return 'text-bg-info';
    if (level.indexOf('三级') !== -1) return 'text-bg-secondary';
    return 'text-bg-light';
  }

  function levelBadgeHtml(level) {
    return level
      ? '<span class="badge ' + levelBadgeClass(level) + '">' + esc(level) + '</span>'
      : '<span class="badge text-bg-light">未定级</span>';
  }

  /* ===================== 2. API 客户端 ===================== */
  const API_BASE = '';        // 与后端同源部署，留空即可
  let redirecting = false;    // 防止 401 时重复跳转

  /**
   * 统一请求：自动带 Cookie、自动解析 { code, message, data }
   * code != 0 一律抛异常，调用方用 try/catch 接。
   */
  async function request(path, options) {
    let response;
    try {
      response = await fetch(API_BASE + path, Object.assign({
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      }, options || {}));
    } catch (err) {
      throw new Error('无法连接后端服务，请确认已启动（python run.py）');
    }

    let body;
    try {
      body = await response.json();
    } catch (err) {
      throw new Error('服务返回异常（HTTP ' + response.status + '），请查看后端日志');
    }

    if (body.code === 401) {
      sessionUser = null;
      const page = document.body ? document.body.getAttribute('data-page') : '';
      if (page !== 'login' && !redirecting) {
        redirecting = true;
        window.location.replace(loginPageUrl());
      }
      const e401 = new Error(body.message || '未登录');
      e401.code = 401;
      throw e401;
    }

    if (body.code !== 0) {
      const e = new Error(body.message || '请求失败');
      e.code = body.code;
      throw e;
    }
    return body.data;
  }

  const api = {
    get: (path) => request(path),
    post: (path, data) => request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(data || {})
    }),
    put: (path, data) => request(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(data || {})
    }),
    del: (path) => request(path, { method: 'DELETE' }),
    /** 上传（FormData）：不要手动设置 Content-Type，浏览器要自己带 boundary */
    upload: (path, formData) => request(path, { method: 'POST', body: formData })
  };

  /** 把查询参数拼成 query string（中文会自动百分号编码） */
  function qs(params) {
    const usp = new URLSearchParams();
    Object.keys(params || {}).forEach(function (key) {
      const value = params[key];
      if (value !== undefined && value !== null && value !== '') usp.append(key, value);
    });
    const text = usp.toString();
    return text ? ('?' + text) : '';
  }

  /* ===================== 3. 会话（服务端签名 Cookie） ===================== */
  let sessionUser = null;
  let sessionPromise = null;

  /** 取当前登录用户（内存缓存 + 后端 /api/auth/me 校验） */
  function loadSession(force) {
    if (sessionUser && !force) return Promise.resolve(sessionUser);
    if (sessionPromise && !force) return sessionPromise;
    sessionPromise = api.get('/api/auth/me')
      .then(function (profile) { sessionUser = profile; return profile; })
      .catch(function () { sessionUser = null; return null; })
      .then(function (value) { sessionPromise = null; return value; });
    return sessionPromise;
  }

  /** 每个"需要登录"的页面进来先调用一次：没登录会被跳到登录页 */
  async function requireLogin(requiredRole) {
    const user = await loadSession();
    if (!user) return null;      // request() 里已经跳转了
    if (requiredRole && user.role !== requiredRole) {
      // 角色和当前区域不符（比如学生打开了管理页），送回属于他的首页
      const home = upPrefix() + (user.role === 'ADMIN' ? 'admin/dashboard.html' : 'student/dashboard.html');
      window.location.replace(home);
      return null;
    }
    return user;
  }

  /** 把登录用户信息填到导航栏（元素上有 data-user-name / data-user-no） */
  function fillStudentBar(user) {
    $$('[data-user-name]').forEach(function (node) { node.textContent = user.name + '同学'; });
    $$('[data-user-no]').forEach(function (node) { node.textContent = user.username; });
  }

  /** 切换登录/注册 tab（Bootstrap 的 Tab 组件） */
  function switchTab(tabId) {
    const el = byId(tabId);
    if (el && window.bootstrap) new bootstrap.Tab(el).show();
  }

  /* ===================== 4. 全局通用按钮 ===================== */
  function initCommonActions() {
    // 退出登录：清掉服务端会话，再回登录页
    $$('[data-action="logout"]').forEach(function (btn) {
      btn.addEventListener('click', async function (e) {
        e.preventDefault();
        if (!confirm('确定要退出登录吗？')) return;
        try { await api.post('/api/auth/logout'); } catch (err) { /* 退出失败也照样回登录页 */ }
        sessionUser = null;
        window.location.replace(loginPageUrl());
      });
    });

    // 导出当前表格为 CSV（Excel 可直接打开）
    $$('[data-action="export"]').forEach(function (btn) {
      btn.addEventListener('click', function () { exportTableCsv(btn); });
    });
  }

  function exportTableCsv(btn) {
    let table = btn.closest('table');
    if (!table) {
      const host = btn.closest('.card') || btn.closest('main') || document.body;
      table = host.querySelector('table');
    }
    if (!table) return;
    const rows = Array.from(table.querySelectorAll('tr')).map(function (tr) {
      return Array.from(tr.children)
        .map(function (td) { return '"' + String(td.innerText || '').trim().replace(/"/g, '""') + '"'; })
        .join(',');
    });
    const csv = '\ufeff' + rows.join('\r\n');   // \ufeff 让 Excel 正确识别 UTF-8
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    a.download = (document.title || 'export') + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  /* ============================================================
   * 5. 登录 / 注册页（login.html）
   * ============================================================ */
  async function initLoginPage() {
    const loginMsg = byId('loginMsg');

    function showMsg(kind, text) {
      if (!loginMsg) return;
      loginMsg.className = 'alert alert-' + kind + ' py-2 small';
      loginMsg.innerHTML = text;
      loginMsg.classList.remove('d-none');
    }
    function hideMsg() { if (loginMsg) loginMsg.classList.add('d-none'); }

    function goHome(role) {
      window.location.href = (role === 'ADMIN') ? 'admin/dashboard.html' : 'student/dashboard.html';
    }

    // 已经登录过就直接进对应首页
    const existing = await loadSession();
    if (existing) { goHome(existing.role); return; }

    // ---------- 登录 ----------
    const formLogin = byId('formLogin');
    if (formLogin) {
      formLogin.addEventListener('submit', async function (e) {
        e.preventDefault();
        hideMsg();
        const username = (byId('loginName').value || '').trim();
        const password = byId('loginPwd').value;
        if (!username || !password) { showMsg('danger', '请输入账号和密码'); return; }

        const btn = byId('btnLogin');
        const raw = btn ? btn.innerHTML : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>登录中…'; }
        try {
          const user = await api.post('/api/auth/login', { username: username, password: password });
          sessionUser = user;
          goHome(user.role);
        } catch (err) {
          showMsg('danger', esc(err.message));
          if (btn) { btn.disabled = false; btn.innerHTML = raw; }
        }
      });
    }

    // 演示账号快捷填充
    $$('.demo-fill').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (btn.getAttribute('data-role') === 'admin') {
          byId('loginName').value = 'admin';
          byId('loginPwd').value = 'admin123';
        } else {
          byId('loginName').value = '2024001';
          byId('loginPwd').value = '123456';
        }
      });
    });

    // ---------- 注册（只开放给学生） ----------
    const formRegister = byId('formRegister');
    if (formRegister) {
      formRegister.addEventListener('submit', async function (e) {
        e.preventDefault();
        hideMsg();
        const name = (byId('regName').value || '').trim();
        const studentNo = (byId('regStudentNo').value || '').trim();
        const className = (byId('regClass').value || '').trim();
        const pwd = byId('regPwd').value;
        const pwd2 = byId('regPwd2').value;

        if (!name || !studentNo || !className) { showMsg('danger', '请把姓名、学号、班级填写完整'); return; }
        if (pwd.length < 6 || pwd.length > 20) { showMsg('danger', '密码长度需在 6-20 位之间'); return; }
        if (pwd !== pwd2) { showMsg('danger', '两次输入的密码不一致'); return; }

        const btn = byId('btnRegister');
        const raw = btn ? btn.innerHTML : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>提交中…'; }
        try {
          await api.post('/api/auth/register', {
            name: name,
            student_no: studentNo,
            class_name: className,
            password: pwd
          });
          byId('loginName').value = studentNo;   // 顺手帮你填好学号
          byId('loginPwd').value = '';
          byId('regPwd').value = '';
          byId('regPwd2').value = '';
          switchTab('loginTab');
          showMsg('success', '注册成功，请用学号 <b>' + esc(studentNo) + '</b> 登录');
        } catch (err) {
          showMsg('danger', esc(err.message));
        } finally {
          if (btn) { btn.disabled = false; btn.innerHTML = raw; }
        }
      });
    }
  }

  /* ============================================================
   * 6. 学生端：我的考试首页（student/dashboard.html）
   * ============================================================ */
  function avgOf(nums) {
    if (!nums.length) return 0;
    return round1(nums.reduce(function (s, n) { return s + n; }, 0) / nums.length);
  }
  function maxOf(nums) { return nums.reduce(function (m, n) { return Math.max(m, n); }, 0); }
  function minOf(nums) { return nums.reduce(function (m, n) { return Math.min(m, n); }, 100); }

  async function initStudentDashboard() {
    const user = await requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);
    setText('hiName', '你好，' + user.name + '同学');
    setText('bannerNo', '学号 ' + user.username);

    let data;
    try {
      data = await api.get('/api/student/dashboard');
    } catch (err) {
      alert('加载首页数据失败：' + err.message);
      return;
    }

    const count = data.exam_count || 0;
    setText('statExamCount', count);
    setText('statAvgScore', data.avg_score === null || data.avg_score === undefined ? '--' : fmtScore(data.avg_score));
    setText('statMaxScore', data.max_score === null || data.max_score === undefined ? '--' : fmtScore(data.max_score));
    setText('statCurrentLevel', data.current_level || '--');
    setHtml('headerLevel', data.current_level ? levelBadgeHtml(data.current_level) : '<span class="badge text-bg-light">未定级</span>');

    const recent = data.recent_exams || [];
    const box = byId('recentList');
    if (box) {
      box.innerHTML = recent.length ? recent.map(function (item) {
        return '<a class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" href="report.html?record_id=' + encodeURIComponent(item.record_id) + '">' +
          '<span class="small">' + esc(shortDate(item.date)) + '</span>' +
          '<span><span class="fw-bold text-success-score me-2">' + fmtScore(item.score) + ' 分</span>' +
          levelBadgeHtml(item.level) + '</span></a>';
      }).join('') : '<li class="list-group-item text-secondary small">还没有考试记录，点击上方按钮考一场吧</li>';
    }
  }

  /* ============================================================
   * 7. 学生端：历史成绩 + 折线图（student/history.html）
   * ============================================================ */
  function drawScoreLine(el, dates, scores) {
    if (!el || typeof echarts === 'undefined' || !scores.length) return;
    const chart = echarts.init(el);
    const minVal = Math.min.apply(null, scores);
    const maxVal = Math.max.apply(null, scores);
    const yMin = Math.max(0, Math.floor((minVal - 3) / 10) * 10);
    const yMax = Math.min(100, Math.ceil((maxVal + 3) / 10) * 10);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 30, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: dates.map(function (d) { return String(d || '').slice(5, 10); }), axisLine: { lineStyle: { color: '#cbd5e1' } } },
      yAxis: { type: 'value', min: yMin, max: yMax, name: '分', axisLine: { lineStyle: { color: '#cbd5e1' } }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
      series: [{
        name: '总分', type: 'line', smooth: true, symbolSize: 8,
        data: scores,
        lineStyle: { width: 3, color: '#1E3A8A' },
        itemStyle: { color: '#1E3A8A' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(30,58,138,.25)' }, { offset: 1, color: 'rgba(30,58,138,.02)' }] } },
        markPoint: { data: [{ type: 'max', name: '最高分' }, { type: 'min', name: '最低分' }] },
        markLine: { data: [{ type: 'average', name: '平均分' }], lineStyle: { color: '#10B981', type: 'dashed' } }
      }]
    });
    window.addEventListener('resize', function () { chart.resize(); });
  }

  function renderHistoryTable(list) {
    const body = byId('historyTbody');
    if (!body) return;
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="8" class="text-center text-secondary small py-4">暂无考试记录，<a href="exam.html">去考一场</a>吧</td></tr>';
      return;
    }
    body.innerHTML = list.map(function (rec) {
      const parts = (rec.sections || []).map(function (s) { return s.score; });
      return '<tr>' +
        '<td>' + esc(shortDate(rec.finished_at)) + '</td>' +
        '<td class="fw-bold text-success-score">' + fmtScore(rec.total_score) + '</td>' +
        '<td>' + levelBadgeHtml(rec.level) + '</td>' +
        '<td>' + fmtScore(parts[0]) + '</td>' +
        '<td>' + fmtScore(parts[1]) + '</td>' +
        '<td>' + fmtScore(parts[2]) + '</td>' +
        '<td>' + fmtScore(parts[3]) + '</td>' +
        '<td><a class="btn btn-sm btn-outline-primary" href="report.html?record_id=' + encodeURIComponent(rec.record_id) + '">查看</a></td>' +
        '</tr>';
    }).join('');
  }

  async function initHistoryPage() {
    const user = await requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);

    let list, chart;
    try {
      list = await api.get('/api/exam/records');       // 时间倒序
      chart = await api.get('/api/exam/chart');        // 时间正序，画曲线用
    } catch (err) {
      alert('加载历史成绩失败：' + err.message);
      return;
    }

    const scores = list.map(function (r) { return r.total_score || 0; });
    const count = list.length;
    setText('statCount', count);
    setText('statMax', count ? fmtScore(maxOf(scores)) : '--');
    setText('statMin', count ? fmtScore(minOf(scores)) : '--');
    setText('statAvg', count ? fmtScore(avgOf(scores)) : '--');

    const emptyTip = byId('chartEmpty');
    if (!count) {
      if (emptyTip) emptyTip.classList.remove('d-none');
    } else {
      if (emptyTip) emptyTip.classList.add('d-none');
      drawScoreLine(byId('scoreChart'), chart.dates || [], chart.scores || []);
    }

    renderHistoryTable(list);
  }

  /* ============================================================
   * 8. 学生端：成绩报告（student/report.html）
   * ============================================================ */
  function renderReport(report, user) {
    const finished = report.status === 'FINISHED';

    setText('reportUser', user.name + '（' + user.username + '）');
    setHtml('reportTotal', fmtScore(report.total_score));
    setHtml('reportLevel', levelBadgeHtml(report.level));
    setHtml('reportStatus', finished
      ? '<span class="badge text-bg-success fs-6">已完成</span>'
      : '<span class="badge text-bg-warning fs-6">进行中</span>');
    setText('reportMeta', '开始时间：' + orDash(report.started_at) + (finished ? '　·　交卷时间：' + orDash(report.finished_at) : ''));

    const sections = report.sections || [];
    const cards = byId('sectionCards');
    if (cards) {
      cards.innerHTML = sections.map(function (s) {
        const pct = (s.score === null || s.score === undefined) ? 0 : Math.round((s.score / s.total) * 100);
        return '<div class="col-6 col-lg-3"><div class="card h-100"><div class="card-body">' +
          '<div class="text-secondary small mb-1">' + esc(s.title) + '</div>' +
          '<div class="fs-3 fw-bold text-success-score">' + fmtScore(s.score) + ' <span class="fs-6 text-secondary">/ ' + fmtScore(s.total) + '</span></div>' +
          '<div class="progress mt-2" style="height:6px"><div class="progress-bar bg-success" style="width:' + pct + '%"></div></div>' +
          '</div></div></div>';
      }).join('');
    }

    const detail = byId('detailTbody');
    if (detail) {
      detail.innerHTML = sections.map(function (s) {
        const d = s.detail || {};
        return '<tr>' +
          '<td><span class="badge badge-level">' + esc(s.title) + '</span></td>' +
          '<td><span class="fw-bold text-success-score">' + orDash(d.shengmu) + '%</span></td>' +
          '<td><span class="fw-bold text-success-score">' + orDash(d.yunmu) + '%</span></td>' +
          '<td><span class="fw-bold text-success-score">' + orDash(d.shengdiao) + '%</span></td>' +
          '</tr>';
      }).join('');
    }
  }

  async function initReportPage() {
    const user = await requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);

    const recordId = queryParam('record_id') || queryParam('recordId');

    let report = null;
    try {
      if (recordId) {
        report = await api.get('/api/exam/records/' + encodeURIComponent(recordId));
      } else {
        // URL 没带 id：默认取当前学生最近一次成绩
        const list = await api.get('/api/exam/records');
        if (list.length) report = await api.get('/api/exam/records/' + list[0].record_id);
      }
    } catch (err) {
      const content = byId('reportContent');
      if (content) content.classList.add('d-none');
      setHtml('reportEmpty', '<div class="text-center py-5"><i class="bi bi-exclamation-triangle fs-1 text-warning"></i>' +
        '<p class="mt-3 text-secondary">' + esc(err.message) + '</p>' +
        '<a class="btn btn-primary" href="dashboard.html">返回首页</a></div>');
      byId('reportEmpty').classList.remove('d-none');
      return;
    }

    if (!report) {
      setHtml('reportEmpty', '<div class="text-center py-5"><i class="bi bi-inbox fs-1 text-secondary"></i><p class="mt-3 text-secondary">还没有考试记录</p><a class="btn btn-primary" href="exam.html">去考一场</a></div>');
      const content = byId('reportContent');
      if (content) content.classList.add('d-none');
      byId('reportEmpty').classList.remove('d-none');
      return;
    }

    renderReport(report, user);
  }
  /* ============================================================
   * 9. 学生端：考试页（student/exam.html）
   *    服务端随机组卷 -> 逐题上传录音 -> 服务端评分 -> 交卷
   * ============================================================ */
  let examState = null;           // 本次考试页面状态
  let examTimer = null;           // 整场倒计时
  let mediaRecorder = null;
  let audioChunks = [];
  let recTimer = null;
  let recSeconds = 0;
  let finishAfterSubmit = false;  // 时间到时：提交完本题立即交卷

  function isTypeDone(sess, type) {
    return !!(sess && sess.results && sess.results[type]);
  }
  function pendingTypes(paper, sess) {
    return paper.sections.filter(function (s) { return !isTypeDone(sess, s.type); });
  }
  function nextPending(paper, sess, afterType) {
    const pending = pendingTypes(paper, sess).map(function (s) { return s.type; });
    if (!pending.length) return null;
    const later = pending.filter(function (t) { return t > afterType; });
    return later.length ? later[0] : pending[0];
  }
  function sectionOfType(paper, type) {
    for (let i = 0; i < paper.sections.length; i++) {
      if (paper.sections[i].type === type) return paper.sections[i];
    }
    return paper.sections[0];
  }
  /** 默认进入第一道没提交的题；URL 里带了 type 就按 type 进 */
  function resolveCurrentType(paper, sess) {
    const fromParam = parseInt(queryParam('type'), 10);
    if (fromParam >= 1 && fromParam <= 4) return fromParam;
    const first = pendingTypes(paper, sess);
    return first.length ? first[0].type : paper.sections[0].type;
  }

  async function initExamPage() {
    const user = await requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);
    setText('stuName', user.name);
    setText('stuNo', user.username);

    let paper, report;
    try {
      paper = await api.post('/api/exam/start');                       // 服务端组卷（未交卷则接着考）
      report = await api.get('/api/exam/records/' + paper.record_id);  // 已作答的题从成绩里恢复
    } catch (err) {
      alert('加载试卷失败：' + err.message);
      return;
    }

    const results = {};
    (report.sections || []).forEach(function (s) {
      if (s.score !== null && s.score !== undefined) {
        results[s.type] = { score: s.score, total: s.total, detail: s.detail || {} };
      }
    });

    // 截止时间由"服务端开始时间 + 总时长"推导，刷新/切题都不会重置
    const startedAt = parseDateTime(report.started_at) || new Date();
    const deadline = startedAt.getTime() + (paper.duration_seconds || 780) * 1000;

    const sess = { record_id: paper.record_id, results: results, deadline: deadline };
    examState = {
      user: user,
      paper: paper,
      sess: sess,
      curType: resolveCurrentType(paper, sess),
      busy: false,
      finished: false
    };

    renderExamNav();
    renderSection(sectionOfType(paper, examState.curType));
    renderRecordPanel();
    startGlobalClock();
  }


  /* ---------- 左侧题型导航 ---------- */
  function renderExamNav() {
    const nav = byId('examNav');
    if (!nav) return;
    nav.innerHTML = examState.paper.sections.map(function (s) {
      const done = isTypeDone(examState.sess, s.type);
      let right;
      if (done) {
        right = '<span class="text-success small"><i class="bi bi-check-circle-fill"></i> ' +
          fmtScore(examState.sess.results[s.type].score) + '分</span>';
      } else if (s.type === examState.curType) {
        right = '<span class="badge text-bg-primary">进行中</span>';
      } else {
        right = '<span class="text-secondary small">未开始</span>';
      }
      const active = (s.type === examState.curType) ? ' active' : '';
      const icon = done ? 'bi-check-circle-fill text-success' : 'bi-record-circle';
      return '<a href="exam.html?type=' + s.type + '" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center' + active + '">' +
        '<span><i class="bi ' + icon + ' me-2"></i>' + esc(s.name || TYPE_NAMES[s.type]) + '</span>' + right + '</a>';
    }).join('');
  }

  /* ---------- 中间题目区 ---------- */
  function renderSection(section) {
    setText('examTitle', section.title);
    setText('examMeta', '限时 ' + section.limit_text + '，共 ' + section.count_text);
    setText('examTip', section.tip);

    const info = byId('typeInfo');
    if (info) {
      info.innerHTML =
        '<li class="list-group-item d-flex justify-content-between"><span>类型</span><span class="fw-semibold">' + esc(section.title) + '</span></li>' +
        '<li class="list-group-item d-flex justify-content-between"><span>题量</span><span class="fw-semibold">' + esc(section.count_text) + '</span></li>' +
        '<li class="list-group-item d-flex justify-content-between"><span>限时</span><span class="fw-semibold">' + esc(section.limit_text) + '</span></li>';
    }

    const box = byId('questionBox');
    if (!box) return;
    const items = section.items || [];
    if (section.type === 1 || section.type === 2) {
      box.innerHTML = '<div class="exam-words">' + items.map(function (w) {
        return '<span class="word-cell">' + esc(w) + '</span>';
      }).join('') + '</div>';
    } else if (section.type === 3) {
      box.innerHTML = '<p class="exam-passage mb-0">' + esc(items[0] || '') + '</p>';
    } else {
      box.innerHTML = '<div class="exam-topic mb-3">' + esc(items[0] || '未命名话题') + '</div>' +
        '<div class="alert alert-info border-0 small mb-0"><i class="bi bi-lightbulb me-1"></i>' + esc(section.tip || '') + '</div>';
    }
  }

  /* ---------- 提交反馈区 ---------- */
  function feedbackHtml(html, cls) {
    const wrap = byId('submitResult');
    if (wrap) wrap.innerHTML = html ? '<div class="alert ' + cls + ' text-start mt-3 mb-0">' + html + '</div>' : '';
  }

  function summaryHtml(res, withAutoHint) {
    const pct = (res && res.total) ? Math.round((res.score / res.total) * 100) : 0;
    const pending = pendingTypes(examState.paper, examState.sess);
    const detail = res.detail || {};
    const detailText = '声母 ' + orDash(detail.shengmu) + '%　·　韵母 ' + orDash(detail.yunmu) + '%　·　声调 ' + orDash(detail.shengdiao) + '%';
    let action;
    if (pending.length) {
      const next = nextPending(examState.paper, examState.sess, examState.curType);
      action = '<a class="btn btn-sm btn-outline-primary mt-2" href="exam.html?type=' + next + '"><i class="bi bi-arrow-right me-1"></i>继续下一题</a>';
    } else {
      action = '<button type="button" class="btn btn-sm btn-success mt-2" id="btnFinishNow"><i class="bi bi-check2-circle me-1"></i>交卷并查看成绩</button>';
    }
    return '<div class="d-flex justify-content-between align-items-center">' +
      '<span><i class="bi bi-check-circle-fill me-1 text-success"></i>第 ' + examState.curType + ' 题提交成功</span>' +
      '<span class="fw-bold text-success-score">' + fmtScore(res.score) + ' / ' + fmtScore(res.total) + '</span></div>' +
      '<div class="progress mt-2" style="height:8px"><div class="progress-bar bg-success" style="width:' + pct + '%"></div></div>' +
      '<div class="small text-secondary mt-1">' + detailText + '</div>' +
      (withAutoHint ? '<div class="small text-secondary mt-2">' + (pending.length ? '即将自动进入下一题…' : '四题已提交，即将自动交卷…') + '</div>' : '') +
      action;
  }

  /** 打开页面时，如果当前题已经提交过，就直接显示成绩卡片 */
  function showSubmittedSummary() {
    const res = examState.sess.results[examState.curType];
    if (!res) return;
    feedbackHtml(summaryHtml(res, false), 'alert-success');
    const finishBtn = byId('btnFinishNow');
    if (finishBtn) finishBtn.onclick = doFinishExam;
  }

  /** 提交成功后的处理：2.5 秒后自动进入下一题（或交卷） */
  function showSubmitSuccess(res) {
    renderExamNav();
    feedbackHtml(summaryHtml(res, true), 'alert-success');

    const finishBtn = byId('btnFinishNow');
    if (finishBtn) finishBtn.onclick = doFinishExam;

    clearTimeout(examState.autoTimer);
    examState.autoTimer = setTimeout(function () {
      const pending = pendingTypes(examState.paper, examState.sess);
      if (pending.length) {
        window.location.href = 'exam.html?type=' + nextPending(examState.paper, examState.sess, examState.curType);
      } else {
        doFinishExam();
      }
    }, 2500);
  }

  /* ---------- 录音控制区 ---------- */
  function renderRecordPanel() {
    const startBtn = byId('btnStartRec');
    const stopBtn = byId('btnStopRec');
    if (!startBtn || !stopBtn) return;

    startBtn.onclick = null;
    stopBtn.onclick = null;

    if (isTypeDone(examState.sess, examState.curType)) {
      startBtn.disabled = true;
      stopBtn.disabled = true;
      setRecState('<i class="bi bi-check-circle-fill text-success me-1"></i>本题已提交');
      showSubmittedSummary();
    } else {
      startBtn.disabled = false;
      stopBtn.disabled = true;
      startBtn.onclick = onStartRec;
      stopBtn.onclick = onStopRec;
      setRecState('<i class="bi bi-circle me-1"></i>未开始');
      feedbackHtml('', '');
    }
  }

  function setRecState(html) {
    const node = byId('recState');
    if (node) node.innerHTML = html;
  }

  /** 开始录音；麦克风不可用时退化为"静音提交"（模拟评分阶段足够用） */
  async function onStartRec() {
    if (!examState || examState.busy || isTypeDone(examState.sess, examState.curType)) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
      alert('当前浏览器不支持录音，将直接提交本题（模拟评分阶段，不影响体验）。');
      await uploadSection(null);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true } });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      mediaRecorder.ondataavailable = function (e) {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = onRecorderStopped;
      mediaRecorder.start();

      byId('btnStartRec').disabled = true;
      byId('btnStopRec').disabled = false;
      recSeconds = 0;
      setRecState('<span class="pulse"></span>正在录音… <span class="fw-bold" id="recClock">00:00</span>');
      clearInterval(recTimer);
      recTimer = setInterval(function () {
        recSeconds++;
        const clock = byId('recClock');
        if (clock) clock.textContent = fmtClock(recSeconds);
      }, 1000);
    } catch (err) {
      alert('无法打开麦克风：' + (err.message || err) + '\n将直接提交本题。');
      await uploadSection(null);
    }
  }

  /** MediaRecorder 停止后触发 */
  function onRecorderStopped() {
    clearInterval(recTimer);
    if (mediaRecorder && mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach(function (track) { track.stop(); });
    }
    const blob = audioChunks.length ? new Blob(audioChunks, { type: 'audio/webm' }) : null;
    uploadSection(blob);
  }

  function onStopRec() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      setRecState('<span class="spinner-border spinner-border-sm me-1"></span>正在上传评分…');
      mediaRecorder.stop();
    }
  }

  /**
   * 把浏览器录到的音频（webm/opus、mp4/aac…）转成讯飞要求的 16k / 16bit / 单声道 PCM。
   * 麦克风通常是 44.1k/48k 双声道，而讯飞只认 16k 单声道，所以必须先解码重采样，
   * 不能直接把 MediaRecorder 的原始文件传上去。
   */
  async function toIsePcm(blob) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!Ctx || !Offline) throw new Error('当前浏览器不支持音频转码');

    const ctx = new Ctx();
    let decoded;
    try {
      decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    } finally {
      if (ctx.close) ctx.close();
    }

    const frames = Math.max(1, Math.ceil(decoded.duration * 16000));
    const offline = new Offline(1, frames, 16000);   // 目标 1 声道：浏览器会自动下混
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();

    const channel = rendered.getChannelData(0);
    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i++) {
      const sample = Math.max(-1, Math.min(1, channel[i]));
      pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return new Blob([pcm.buffer], { type: 'application/octet-stream' });
  }
  /** 提交当前题型：录音以 multipart 上传，评分由后端完成 */
  async function uploadSection(audioBlob) {
    if (!examState || examState.busy) return;
    const type = examState.curType;
    examState.busy = true;

    const startBtn = byId('btnStartRec');
    const stopBtn = byId('btnStopRec');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
    clearInterval(recTimer);
    feedbackHtml('<span class="spinner-border spinner-border-sm me-2"></span>正在提交并评分…', 'alert-secondary');

    try {
      // 讯飞要求 16k/16bit/单声道裸 PCM：先把浏览器录到的音频转码
      let payload = new Blob([], { type: 'application/octet-stream' });
      if (audioBlob && audioBlob.size > 0) {
        feedbackHtml('<span class="spinner-border spinner-border-sm me-2"></span>正在处理录音…', 'alert-secondary');
        try {
          payload = await toIsePcm(audioBlob);
        } catch (err) {
          throw new Error('录音转码失败：' + (err.message || err) + '（请用 Chrome / Edge 重新录制本题）');
        }
      }

      const form = new FormData();
      form.append('recordId', String(examState.sess.record_id));
      form.append('type', String(type));
      form.append('file', payload, 'rec_' + type + '.pcm');
      const result = await api.upload('/api/exam/submit', form);

      examState.sess.results[type] = {
        score: result.score,
        total: result.total,
        detail: result.detail || {}
      };
      examState.busy = false;

      if (finishAfterSubmit) {
        finishAfterSubmit = false;
        doFinishExam();
        return;
      }
      showSubmitSuccess(examState.sess.results[type]);
    } catch (err) {
      examState.busy = false;
      // code=410：服务端判定本场考试已经超时（前端倒计时可能与服务端不一致），
      // 并且已经自动交卷，这里直接带学生去成绩页，不要再让他重录。
      if (err.code === 410) {
        setRecState('<i class="bi bi-clock-history text-warning me-1"></i>' + esc(err.message));
        alert(err.message + '，即将跳转到成绩页…');
        window.location.href = 'report.html?record_id=' + encodeURIComponent(examState.sess.record_id);
        return;
      }
      // 按业务码给不同的下一步建议：
      //   400 没录到有效语音  -> 重录
      //   429 评测排队已满    -> 等一会儿再交同一题（成绩不会重复计算）
      //   其它                -> 可能是后端/评测服务异常
      let bizHint;
      if (err.code === 400) {
        bizHint = '本题还没拿到有效录音，请安静环境下重新录制后再提交。';
      } else if (err.code === 429) {
        bizHint = '当前提交人数较多，请等 10 秒后再点一次提交，同一题不会重复计分。';
      } else {
        bizHint = '请检查后端服务是否正常，然后刷新页面重试。';
      }
      setRecState('<i class="bi bi-exclamation-triangle-fill text-danger me-1"></i>提交失败：' + esc(err.message));
      if (startBtn) startBtn.disabled = false;
      if (stopBtn) stopBtn.disabled = true;
      feedbackHtml('<i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>提交失败：' + esc(err.message) +
        '<div class="small text-secondary mt-1">' + bizHint + '</div>', 'alert-danger');
    }
  }

  /* ---------- 整场倒计时 ---------- */
  function startGlobalClock() {
    const display = byId('examClock');
    const bar = byId('examProgress');
    clearInterval(examTimer);

    function tick() {
      const total = examState.paper.duration_seconds || 780;
      const remain = Math.max(0, Math.round((examState.sess.deadline - Date.now()) / 1000));
      if (display) {
        display.textContent = fmtCn(remain);
        display.classList.toggle('timer-urgent', remain <= 60);
      }
      if (bar) bar.style.width = ((total - remain) / total * 100) + '%';
      if (remain <= 0) {
        clearInterval(examTimer);
        onExamTimeUp();
      }
    }
    tick();
    examTimer = setInterval(tick, 1000);
  }

  /** 时间到：正在录音就先保存本题，然后交卷 */
  function onExamTimeUp() {
    if (!examState || examState.finished) return;
    const type = examState.curType;
    const recording = mediaRecorder && mediaRecorder.state === 'recording';
    if (!isTypeDone(examState.sess, type) && recording) {
      finishAfterSubmit = true;
      alert('考试时间到！正在保存本题录音并自动交卷…');
      mediaRecorder.stop();
    } else {
      alert('考试时间到！未作答的题目不计分，正在交卷…');
      doFinishExam();
    }
  }

  /** 交卷：后端算总分、定等级 */
  async function doFinishExam() {
    if (!examState || examState.finished) return;
    examState.finished = true;
    clearTimeout(examState.autoTimer);
    clearInterval(examTimer);
    clearInterval(recTimer);
    try {
      feedbackHtml('<span class="spinner-border spinner-border-sm me-2"></span>正在交卷并计算总分…', 'alert-secondary');
      const res = await api.post('/api/exam/' + examState.sess.record_id + '/finish');
      window.location.href = 'report.html?record_id=' + encodeURIComponent(res.record_id);
    } catch (err) {
      examState.finished = false;
      feedbackHtml('<i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>交卷失败：' + esc(err.message), 'alert-danger');
    }
  }
  /* ============================================================
   * 10. 管理端：控制台（admin/dashboard.html）
   * ============================================================ */
  function fillAdminBar(user) {
    $$('[data-user-name]').forEach(function (node) { node.textContent = user.name; });
    $$('[data-user-no]').forEach(function (node) { node.textContent = user.username; });
  }

  async function initAdminDashboard() {
    const user = await requireLogin('ADMIN');
    if (!user) return;
    fillAdminBar(user);

    let stats;
    try {
      stats = await api.get('/api/admin/stats');
    } catch (err) {
      alert('加载统计数据失败：' + err.message);
      return;
    }

    setText('statStudents', Number(stats.student_count || 0).toLocaleString('zh-CN'));
    setText('statQuestions', Number(stats.question_count || 0).toLocaleString('zh-CN'));
    setText('statToday', Number(stats.today_exam_count || 0).toLocaleString('zh-CN'));
    setText('statAvg', stats.avg_score === null || stats.avg_score === undefined ? '--' : fmtScore(stats.avg_score));

    const recent = stats.recent_exams || [];
    const body = byId('recentTbody');
    if (body) {
      body.innerHTML = recent.length ? recent.map(function (r) {
        return '<tr>' +
          '<td>' + esc(r.student_name) + '</td>' +
          '<td>' + esc(r.class_name || '-') + '</td>' +
          '<td class="fw-bold text-success-score">' + fmtScore(r.total_score) + '</td>' +
          '<td>' + levelBadgeHtml(r.level) + '</td>' +
          '<td class="text-secondary small">' + esc(r.finished_at || '') + '</td>' +
          '</tr>';
      }).join('') : '<tr><td colspan="5" class="text-center text-secondary small py-3">暂无已完成的考试</td></tr>';
    }

    drawTypeAvgChart(stats.type_averages || []);
  }

  /** ECharts 柱状图：各题型得分率（得分 / 该题满分） */
  function drawTypeAvgChart(list) {
    const el = byId('typeScoreChart');
    const emptyTip = byId('typeChartEmpty');
    if (!el) return;
    if (!list.length) {
      if (emptyTip) emptyTip.classList.remove('d-none');
      return;
    }
    if (emptyTip) emptyTip.classList.add('d-none');
    if (typeof echarts === 'undefined') return;

    const rows = list.map(function (item) {
      const total = item.total || TYPE_TOTAL[item.type] || 100;
      return {
        name: item.name || TYPE_NAMES[item.type] || ('题' + item.type),
        pct: Math.round((item.avg / total) * 1000) / 10,
        text: fmtScore(item.avg) + ' / ' + total
      };
    });
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis', formatter: function (p) { return p[0].name + '：' + p[0].data.text + '（得分率 ' + p[0].data.value + '%）'; } },
      grid: { left: 50, right: 30, top: 30, bottom: 40 },
      xAxis: { type: 'category', data: rows.map(function (r) { return r.name; }), axisLine: { lineStyle: { color: '#cbd5e1' } } },
      yAxis: { type: 'value', max: 100, name: '得分率 %', axisLine: { lineStyle: { color: '#cbd5e1' } }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
      series: [{
        type: 'bar', barWidth: '45%',
        data: rows.map(function (r) { return { value: r.pct, text: r.text }; }),
        itemStyle: { color: '#1E3A8A', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: function (p) { return p.data.text; }, color: '#475569' }
      }]
    });
    window.addEventListener('resize', function () { chart.resize(); });
  }

  /* ============================================================
   * 11. 管理端：题库管理（admin/questions.html）
   *     分页 / 题型筛选 / 关键字搜索全部走后端，保证大数据量也不卡
   * ============================================================ */
  const PAGE_SIZE = 10;
  let qState = { page: 1, total_pages: 1, total: 0, rows: [] };

  async function initQuestionAdminPage() {
    const user = await requireLogin('ADMIN');
    if (!user) return;
    fillAdminBar(user);

    const searchInput = byId('questionSearch');
    const btnSearch = byId('btnSearchQuestion');
    const typeFilter = byId('qTypeFilter');
    const pager = byId('questionPageNav');

    function reloadFirstPage() { gotoQuestions(1); }

    if (btnSearch) btnSearch.addEventListener('click', reloadFirstPage);
    if (searchInput) searchInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') reloadFirstPage(); });
    if (typeFilter) typeFilter.addEventListener('change', reloadFirstPage);
    if (pager) pager.addEventListener('click', function (e) {
      const a = e.target.closest('a[data-pg]');
      if (!a) return;
      e.preventDefault();
      if (a.closest('.page-item').classList.contains('disabled')) return;
      gotoQuestions(Number(a.getAttribute('data-pg')));
    });

    const btnAdd = byId('btnAddQuestion');
    if (btnAdd) btnAdd.addEventListener('click', function () { openQuestionModal(null); });

    const body = byId('questionTbody');
    if (body) body.addEventListener('click', onQuestionRowClick);

    // 保存（新增 / 编辑共用）
    const form = byId('formQuestion');
    if (form) {
      form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const id = byId('questionId').value;
        const content = (byId('qContent').value || '').trim();
        if (!content) { alert('题目内容不能为空'); return; }
        const payload = {
          type: Number(byId('qType').value),
          content: content,
          answer: (byId('qAnswer').value || '').trim(),
          difficulty: byId('qLevel').value
        };
        const btn = byId('btnSaveQuestion');
        if (btn) btn.disabled = true;
        try {
          if (id) {
            await api.put('/api/admin/questions/' + encodeURIComponent(id), payload);
          } else {
            await api.post('/api/admin/questions', payload);
          }
          hideModal('questionModal');
          await gotoQuestions(qState.page);
        } catch (err) {
          alert('保存失败：' + err.message);
        } finally {
          if (btn) btn.disabled = false;
        }
      });
    }

    // 上传 Excel 题库：交给后端 openpyxl 解析
    const excelInput = byId('questionExcel');
    if (excelInput) {
      excelInput.addEventListener('change', async function () {
        const file = excelInput.files && excelInput.files[0];
        if (!file) return;
        const label = byId('uploadLabel');
        if (label) label.textContent = file.name;
        try {
          const form2 = new FormData();
          form2.append('file', file);
          const res = await api.upload('/api/admin/questions/upload', form2);
          alert('导入成功，新增 ' + (res.added || 0) + ' 条题目。');
          await gotoQuestions(1);
        } catch (err) {
          alert('导入失败：' + err.message);
        } finally {
          excelInput.value = '';
          if (label) label.textContent = '上传题库 Excel';
        }
      });
    }

    await gotoQuestions(1);
  }

  function hideModal(id) {
    const modalEl = byId(id);
    if (modalEl && window.bootstrap) {
      const inst = bootstrap.Modal.getInstance(modalEl);
      if (inst) inst.hide();
    }
  }

  async function gotoQuestions(page) {
    if (page < 1) return;
    const filterVal = byId('qTypeFilter') ? byId('qTypeFilter').value : '';
    const kw = byId('questionSearch') ? (byId('questionSearch').value || '').trim() : '';

    let data;
    try {
      data = await api.get('/api/admin/questions' + qs({ type: filterVal, keyword: kw, page: page, size: PAGE_SIZE }));
    } catch (err) {
      alert('查询题库失败：' + err.message);
      return;
    }
    qState = {
      page: data.page || 1,
      total_pages: data.total_pages || 1,
      total: data.total || 0,
      rows: data.list || []
    };
    renderQuestions();
  }

  function renderQuestions() {
    const body = byId('questionTbody');
    if (body) {
      body.innerHTML = qState.rows.length ? qState.rows.map(function (q) {
        const content = q.content || '';
        const answer = (q.answer || '') || '-';
        const contentShow = content.length > 55 ? content.slice(0, 55) + '…' : content;
        const answerShow = answer.length > 35 ? answer.slice(0, 35) + '…' : answer;
        return '<tr>' +
          '<td>' + q.id + '</td>' +
          '<td><span class="badge badge-level">' + esc(TYPE_NAMES[q.type] || ('题' + q.type)) + '</span></td>' +
          '<td title="' + esc(content) + '">' + esc(contentShow) + '</td>' +
          '<td class="text-secondary small" title="' + esc(answer) + '">' + esc(answerShow) + '</td>' +
          '<td>' + esc(q.difficulty || '-') + '</td>' +
          '<td class="text-secondary small">' + esc((q.updated_at || '').slice(0, 16)) + '</td>' +
          '<td class="text-nowrap">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1" data-edit="' + q.id + '"><i class="bi bi-pencil-square"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger" data-del="' + q.id + '"><i class="bi bi-trash"></i></button>' +
          '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="text-center text-secondary small py-4">没有符合条件的题目</td></tr>';
    }

    const info = byId('questionPageInfo');
    if (info) info.textContent = '共 ' + qState.total + ' 条，第 ' + qState.page + ' / ' + qState.total_pages + ' 页';

    const pager = byId('questionPageNav');
    if (pager) {
      let lis = '<li class="page-item' + (qState.page <= 1 ? ' disabled' : '') + '"><a class="page-link" href="#" data-pg="' + (qState.page - 1) + '">«</a></li>';
      for (let i = 1; i <= qState.total_pages; i++) {
        if (qState.total_pages > 9 && i !== 1 && i !== qState.total_pages && Math.abs(i - qState.page) > 2) {
          if (lis.indexOf('…</span></li>') === -1) lis += '<li class="page-item disabled"><span class="page-link">…</span></li>';
          continue;
        }
        lis += '<li class="page-item' + (i === qState.page ? ' active' : '') + '"><a class="page-link" href="#" data-pg="' + i + '">' + i + '</a></li>';
      }
      lis += '<li class="page-item' + (qState.page >= qState.total_pages ? ' disabled' : '') + '"><a class="page-link" href="#" data-pg="' + (qState.page + 1) + '">»</a></li>';
      pager.innerHTML = lis;
    }
  }

  function findQuestionInRows(id) {
    for (let i = 0; i < qState.rows.length; i++) {
      if (String(qState.rows[i].id) === String(id)) return qState.rows[i];
    }
    return null;
  }

  async function onQuestionRowClick(e) {
    const editBtn = e.target.closest('[data-edit]');
    if (editBtn) {
      openQuestionModal(findQuestionInRows(editBtn.getAttribute('data-edit')));
      return;
    }
    const delBtn = e.target.closest('[data-del]');
    if (delBtn) {
      if (!confirm('确认删除该题目？删除后不可恢复。')) return;
      try {
        await api.del('/api/admin/questions/' + encodeURIComponent(delBtn.getAttribute('data-del')));
      } catch (err) {
        alert('删除失败：' + err.message);
        return;
      }
      const target = (qState.rows.length === 1 && qState.page > 1) ? qState.page - 1 : qState.page;
      await gotoQuestions(target);
    }
  }

  function openQuestionModal(q) {
    const modalEl = byId('questionModal');
    if (!modalEl) return;
    setText('questionModalTitle', q ? '编辑题目 #' + q.id : '新增题目');
    byId('questionId').value = q ? q.id : '';
    byId('qType').value = q ? String(q.type) : '1';
    byId('qContent').value = q ? (q.content || '') : '';
    byId('qAnswer').value = q ? (q.answer || '') : '';
    byId('qLevel').value = q ? (q.difficulty || '简单') : '简单';
    if (window.bootstrap) new bootstrap.Modal(modalEl).show();
  }

  /* ============================================================
   * 12. 管理端：学生成绩管理（admin/students.html）
   * ============================================================ */
  let stuRows = [];

  async function initStudentsAdminPage() {
    const user = await requireLogin('ADMIN');
    if (!user) return;
    fillAdminBar(user);

    const searchInput = byId('studentSearch');
    const btnSearch = byId('btnSearchStudent');
    if (btnSearch) btnSearch.addEventListener('click', reloadStudents);
    if (searchInput) searchInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') reloadStudents(); });

    const body = byId('studentTbody');
    if (body) body.addEventListener('click', onStudentRowClick);

    await reloadStudents();
  }

  async function reloadStudents() {
    const kw = byId('studentSearch') ? (byId('studentSearch').value || '').trim() : '';
    let rows;
    try {
      rows = await api.get('/api/admin/students' + qs({ keyword: kw }));
    } catch (err) {
      alert('查询学生失败：' + err.message);
      return;
    }
    stuRows = rows || [];

    const body = byId('studentTbody');
    if (body) {
      body.innerHTML = stuRows.length ? stuRows.map(function (s) {
        return '<tr>' +
          '<td>' + esc(s.student_no || '-') + '</td>' +
          '<td>' + esc(s.name || '-') + '</td>' +
          '<td>' + esc(s.class_name || '-') + '</td>' +
          '<td class="text-secondary small">' + esc(s.last_finished_at ? shortDate(s.last_finished_at) : '-') + '</td>' +
          '<td class="fw-bold text-success-score">' + (s.last_score == null ? '-' : fmtScore(s.last_score)) + '</td>' +
          '<td>' + levelBadgeHtml(s.last_level) + '</td>' +
          '<td><button type="button" class="btn btn-sm btn-outline-primary" data-records-no="' + esc(s.student_no) + '" data-records-name="' + esc(s.name) + '"><i class="bi bi-file-earmark-bar-graph me-1"></i>成绩记录</button></td>' +
          '</tr>';
      }).join('') : '<tr><td colspan="7" class="text-center text-secondary small py-4">没有找到学生</td></tr>';
    }
    setText('studentPageInfo', '共 ' + stuRows.length + ' 名学生');
  }

  function onStudentRowClick(e) {
    const btn = e.target.closest('[data-records-no]');
    if (!btn) return;
    openRecordsModal(btn.getAttribute('data-records-name'), btn.getAttribute('data-records-no'));
  }

  /** 弹窗一：某个学生的历次考试记录 */
  async function openRecordsModal(name, studentNo) {
    const modalEl = byId('recordsModal');
    if (!modalEl) return;

    let list;
    try {
      list = await api.get('/api/admin/students/' + encodeURIComponent(studentNo) + '/records');
    } catch (err) {
      alert('加载成绩记录失败：' + err.message);
      return;
    }

    setText('recordsTitle', name + '（' + studentNo + '）的成绩记录');
    setText('recordsCount', '共 ' + list.length + ' 条记录');
    if (window.bootstrap) new bootstrap.Modal(modalEl).show();

    const body = byId('recordsTbody');
    if (body) {
      body.innerHTML = list.length ? list.map(function (r) {
        return '<tr>' +
          '<td>' + esc(r.finished_at || '') + '</td>' +
          '<td class="fw-bold text-success-score">' + fmtScore(r.total_score) + '</td>' +
          '<td>' + levelBadgeHtml(r.level) + '</td>' +
          '<td><button type="button" class="btn btn-sm btn-outline-primary" data-record-id="' + r.record_id + '" data-record-name="' + esc(name) + '" data-record-no="' + esc(studentNo) + '"><i class="bi bi-eye me-1"></i>查看报告</button></td>' +
          '</tr>';
      }).join('') : '<tr><td colspan="4" class="text-center text-secondary small py-3">该学生还没有完成任何考试</td></tr>';

      body.querySelectorAll('[data-record-id]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          openReportModal(
            btn.getAttribute('data-record-name'),
            btn.getAttribute('data-record-no'),
            btn.getAttribute('data-record-id')
          );
        });
      });
    }
  }

  /** 弹窗二：任意一场考试的完整报告（管理员视角） */
  async function openReportModal(name, no, recordId) {
    let report;
    try {
      report = await api.get('/api/admin/exam-records/' + encodeURIComponent(recordId));
    } catch (err) {
      alert('加载成绩报告失败：' + err.message);
      return;
    }

    // 先关掉"记录列表"弹窗，再开"报告"弹窗
    const recordsModal = byId('recordsModal');
    if (recordsModal && window.bootstrap) {
      const inst = bootstrap.Modal.getInstance(recordsModal);
      if (inst) inst.hide();
    }

    const modalEl = byId('reportModal');
    if (!modalEl) return;

    setText('rpName', name || report.student_name || '-');
    setText('rpNo', no || report.student_no || '-');
    setText('rpClass', report.class_name || '-');
    setText('rpDate', report.finished_at || report.started_at || '-');
    setText('rpTotal', fmtScore(report.total_score));
    setHtml('rpLevel', levelBadgeHtml(report.level));

    const sections = report.sections || [];
    const secBox = byId('rpSections');
    if (secBox) {
      secBox.innerHTML = sections.map(function (s) {
        const pct = (s.score == null) ? 0 : Math.round((s.score / s.total) * 100);
        return '<div class="d-flex justify-content-between align-items-center"><span class="small">' + esc(s.title) + '</span>' +
          '<span class="small"><b class="text-success-score">' + (s.score == null ? '未作答' : fmtScore(s.score)) + '</b> / ' + fmtScore(s.total) + '</span></div>' +
          '<div class="progress mb-2" style="height:6px"><div class="progress-bar bg-success" style="width:' + pct + '%"></div></div>';
      }).join('');
    }

    const detailBody = byId('rpDetail');
    if (detailBody) {
      detailBody.innerHTML = sections.map(function (s) {
        const d = s.detail || {};
        return '<tr><td>' + esc(s.title) + '</td>' +
          '<td>' + orDash(d.shengmu) + '%</td>' +
          '<td>' + orDash(d.yunmu) + '%</td>' +
          '<td>' + orDash(d.shengdiao) + '%</td></tr>';
      }).join('');
    }

    if (window.bootstrap) new bootstrap.Modal(modalEl).show();
  }

  /* ============================================================
   * 13. 入口页 + 页面路由器：<body data-page="xxx">
   * ============================================================ */
  async function initHomePage() {
    const user = await loadSession();
    if (!user) return;
    const tip = byId('homeTip');
    if (!tip) return;
    const home = (user.role === 'ADMIN' ? 'admin/dashboard.html' : 'student/dashboard.html');
    tip.innerHTML = '<i class="bi bi-person-check me-1"></i> 检测到已登录：<b>' + esc(user.name) + '</b>' +
      '　<a class="ms-2" href="' + home + '">进入' + (user.role === 'ADMIN' ? '管理端' : '学生端') + ' <i class="bi bi-arrow-right"></i></a>';
    tip.classList.remove('d-none');
  }

  async function runPage() {
    const page = document.body ? document.body.getAttribute('data-page') : '';
    if (!page) return;

    // 退出登录 / 导出按钮每个页面都可能出现，统一先绑好
    initCommonActions();

    try {
      if (page === 'login') { await initLoginPage(); return; }
      if (page === 'home') { await initHomePage(); return; }
      if (page === 'student-dashboard') { await initStudentDashboard(); return; }
      if (page === 'exam') { await initExamPage(); return; }
      if (page === 'report') { await initReportPage(); return; }
      if (page === 'history') { await initHistoryPage(); return; }
      if (page === 'admin-dashboard') { await initAdminDashboard(); return; }
      if (page === 'admin-questions') { await initQuestionAdminPage(); return; }
      if (page === 'admin-students') { await initStudentsAdminPage(); return; }
    } catch (err) {
      alert(err && err.message ? err.message : String(err));
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    runPage().catch(function (err) {
      alert(err && err.message ? err.message : String(err));
    });
  });
})();