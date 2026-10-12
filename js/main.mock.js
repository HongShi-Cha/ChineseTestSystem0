/* ============================================================
 * 国语水平测试系统 - 前端纯展示版（Mock Data）
 *
 * Mock data added, backend calls removed for Python demo.
 *
 * 本文件由「对接真实后端 API」版改造而来：
 *   1. 已彻底移除 fetch / axios / $.ajax / api.get|post|put|del|upload
 *      等所有真实网络请求，页面可直接以静态方式预览，无需任何后端；
 *   2. 所有页面数据替换为内置硬编码 Mock 数据，字段统一改成 Python
 *      社区常用的下划线命名（student_no / class_name / total_score
 *      / finished_at ...），页面渲染代码同步保持一致；
 *   3. 登录注册、题库增删改查、分页搜索筛选、考试模拟评分、成绩报告、
 *      历史成绩图表等全部在前端本地完成（localStorage/sessionStorage）。
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

  /** HTML 转义：Mock 数据塞进 innerHTML 前必须转义 */
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

  /** 秒 -> 03:05 这种格式 */
  function fmtClock(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    return pad2(Math.floor(seconds / 60)) + ':' + pad2(seconds % 60);
  }

  /** 秒 -> 03分05秒 这种格式 */
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

  function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  /** Date -> 'YYYY-MM-DD HH:mm:ss' */
  function fmtDateTime(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds());
  }

  function nowStr() { return fmtDateTime(new Date()); }

  /* ===================== 1. 等级徽章颜色 ===================== */
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

  /** 依据总分给出普通话等级（与现行评分标准一致） */
  function levelOf(totalScore) {
    if (totalScore === null || totalScore === undefined) return '';
    if (totalScore >= 97) return '一级甲等';
    if (totalScore >= 92) return '一级乙等';
    if (totalScore >= 87) return '二级甲等';
    if (totalScore >= 80) return '二级乙等';
    if (totalScore >= 70) return '三级甲等';
    if (totalScore >= 60) return '三级乙等';
    return '不入级';
  }  /* ===================== 2. Mock 数据仓库 ===================== */
  /**
   * 本地存储封装：优先 localStorage，不可用时退回 sessionStorage，
   * 方便以 file:// 直接双击打开预览时也能登录与存取数据。
   */
  const LS_USERS = 'pthcs_mock_users_v1';
  const LS_QUESTIONS = 'pthcs_mock_questions_v1';
  const LS_RECORDS = 'pthcs_mock_records_v1';
  const SS_SESSION = 'pthcs_mock_session_v1';
  const SS_RECORDS = 'pthcs_mock_tab_records_v1';

  function storeGet(store, key) {
    try { return store.getItem(key); } catch (e) { return null; }
  }
  function storeSet(store, key, value) {
    try { store.setItem(key, value); return true; } catch (e) { return false; }
  }
  function storeRemove(store, key) {
    try { store.removeItem(key); } catch (e) { /* 忽略 */ }
  }
  function parseJson(raw, fallback) {
    if (!raw) return fallback;
    try { return JSON.parse(raw); } catch (e) { return fallback; }
  }

  /** 载入一份 JSON（localStorage 与 sessionStorage 都写一份，互为备份） */
  function loadJson(lsKey, ssKey, seedFn) {
    const local = parseJson(storeGet(window.localStorage, lsKey), null);
    const tab = parseJson(storeGet(window.sessionStorage, ssKey), null);
    const value = local || tab || seedFn();
    storeSet(window.localStorage, lsKey, JSON.stringify(value));
    storeSet(window.sessionStorage, ssKey, JSON.stringify(value));
    return value;
  }
  function saveJson(lsKey, ssKey, value) {
    const text = JSON.stringify(value);
    storeSet(window.localStorage, lsKey, text);
    storeSet(window.sessionStorage, ssKey, text);
  }

  /* ---------- Mock 题库：共 24 条示例数据，覆盖四种题型 ---------- */
  function seedQuestions() {
    return [
      { id: 1,  type: 1, content: '爱',          answer: 'ài',               difficulty: '简单', updated_at: '2026-08-01 10:23:11' },
      { id: 2,  type: 1, content: '白',          answer: 'bái',              difficulty: '简单', updated_at: '2026-08-01 10:23:11' },
      { id: 3,  type: 1, content: '春',          answer: 'chūn',             difficulty: '简单', updated_at: '2026-08-02 09:12:40' },
      { id: 4,  type: 1, content: '风',          answer: 'fēng',             difficulty: '简单', updated_at: '2026-08-02 09:12:40' },
      { id: 5,  type: 1, content: '好',          answer: 'hǎo',              difficulty: '简单', updated_at: '2026-08-03 14:05:02' },
      { id: 6,  type: 1, content: '热',          answer: 'rè',               difficulty: '简单', updated_at: '2026-08-03 14:05:02' },
      { id: 7,  type: 1, content: '民',          answer: 'mín',              difficulty: '中等', updated_at: '2026-08-05 16:44:18' },
      { id: 8,  type: 1, content: '山',          answer: 'shān',             difficulty: '中等', updated_at: '2026-08-06 11:30:55' },
      { id: 9,  type: 1, content: '水',          answer: 'shuǐ',             difficulty: '中等', updated_at: '2026-08-06 11:30:55' },
      { id: 10, type: 1, content: '雪',          answer: 'xuě',              difficulty: '困难', updated_at: '2026-08-08 10:02:31' },
      { id: 11, type: 1, content: '音',          answer: 'yīn',              difficulty: '简单', updated_at: '2026-08-10 15:21:09' },
      { id: 12, type: 1, content: '云',          answer: 'yún',              difficulty: '简单', updated_at: '2026-08-12 09:47:26' },
      { id: 13, type: 2, content: '人民',        answer: 'rén mín',          difficulty: '简单', updated_at: '2026-08-12 09:47:26' },
      { id: 14, type: 2, content: '朋友',        answer: 'péng you',         difficulty: '中等', updated_at: '2026-08-13 17:08:33' },
      { id: 15, type: 2, content: '孩子',        answer: 'hái zi',           difficulty: '中等', updated_at: '2026-08-13 17:08:33' },
      { id: 16, type: 2, content: '花儿',        answer: 'huā ér',           difficulty: '中等', updated_at: '2026-08-15 09:26:12' },
      { id: 17, type: 2, content: '老师',        answer: 'lǎo shī',          difficulty: '简单', updated_at: '2026-08-16 15:08:45' },
      { id: 18, type: 2, content: '聪明',        answer: 'cōng ming',        difficulty: '困难', updated_at: '2026-08-18 13:19:54' },
      { id: 19, type: 3, content: '北京的秋天（短文：秋天是美丽的季节……）', answer: '朗读提示：注意停连、语速适中、语调自然。', difficulty: '中等', updated_at: '2026-08-20 10:11:07' },
      { id: 20, type: 3, content: '读书的乐趣（短文：读书使人充实……）', answer: '朗读提示：注意重音、语气连贯。', difficulty: '困难', updated_at: '2026-08-22 16:40:19' },
      { id: 21, type: 4, content: '我喜欢的季节', answer: '参考提纲：季节特点、喜欢的原因、个人体验。', difficulty: '中等', updated_at: '2026-08-25 11:23:36' },
      { id: 22, type: 4, content: '谈谈个人修养', answer: '参考提纲：什么是修养、身边的例子、如何提升。', difficulty: '中等', updated_at: '2026-08-28 09:50:21' },
      { id: 23, type: 4, content: '我尊敬的人', answer: '参考提纲：人物介绍、印象深刻的事、对我的影响。', difficulty: '困难', updated_at: '2026-09-01 14:32:08' },
      { id: 24, type: 4, content: '我的家乡', answer: '参考提纲：家乡的位置、风土人情、难忘的记忆。', difficulty: '中等', updated_at: '2026-09-03 10:18:47' }
    ];
  }

  /* ---------- Mock 账号（含管理员 + 演示学生） ---------- */
  function seedUsers() {
    return [
      { username: 'admin', password: 'admin123', name: '系统管理员', role: 'ADMIN', student_no: '', class_name: '' },
      { username: '2024001', password: '123456', name: '张三', role: 'STUDENT', student_no: '2024001', class_name: '计算机241' },
      { username: '2024002', password: '123456', name: '李四', role: 'STUDENT', student_no: '2024002', class_name: '计算机241' },
      { username: '2024003', password: '123456', name: '王五', role: 'STUDENT', student_no: '2024003', class_name: '计算机242' },
      { username: '2024004', password: '123456', name: '赵敏', role: 'STUDENT', student_no: '2024004', class_name: '软件工程241' },
      { username: '2024005', password: '123456', name: '孙悦', role: 'STUDENT', student_no: '2024005', class_name: '软件工程242' },
      { username: '2024006', password: '123456', name: '周杰', role: 'STUDENT', student_no: '2024006', class_name: '汉语言241' }
    ];
  }

  /* ---------- Mock 考试记录（含成绩单所需的全部字段） ---------- */
  function userOf(username) {
    const users = seedUsers();
    for (let i = 0; i < users.length; i++) {
      if (users[i].username === username) return users[i];
    }
    return null;
  }

  /** 在本地账号库中查找完整用户档案（含注册的新学生） */
  function profileOf(username) {
    const userList = users();
    for (let i = 0; i < userList.length; i++) {
      if (userList[i].username === username) return userList[i];
    }
    return null;
  }

  /** 由已完成时间（-13 分钟）推算出开始时间 */
  function startedAtOf(finishedStr) {
    const d = new Date(String(finishedStr).replace(' ', 'T'));
    if (isNaN(d.getTime())) return finishedStr;
    d.setSeconds(d.getSeconds() - 780);
    return fmtDateTime(d);
  }

  /** 依据单题得分率生成声母/韵母/声调详情（百分比） */
  function sectionDetail(pct) {
    const p = Math.max(0, Math.min(100, Math.round(pct)));
    return { shengmu: p, yunmu: Math.max(0, p - 2), shengdiao: Math.max(0, p - 4) };
  }

  function seedSection(type, score) {
    const total = TYPE_TOTAL[type] || 100;
    const s = round1(score);
    return { type: type, title: SECTION_TITLES[type], score: s, total: total, detail: sectionDetail(s / total * 100) };
  }

  function mkRecord(student, finishedStr, sectionScores) {
    const sections = sectionScores.map(function (s, idx) { return seedSection(idx + 1, s); });
    const totalScore = round1(sections.reduce(function (sum, s) { return sum + s.score; }, 0));
    return {
      record_id: 'rec_' + student.student_no + '_' + finishedStr.replace(/\D/g, '').slice(0, 14),
      student_no: student.student_no,
      student_name: student.name,
      class_name: student.class_name || '',
      status: 'FINISHED',
      total_score: totalScore,
      level: levelOf(totalScore),
      started_at: startedAtOf(finishedStr),
      finished_at: finishedStr,
      sections: sections
    };
  }

  function seedRecords() {
    const records = [];
    function add(studentNo, rows) {
      const stu = userOf(studentNo);
      rows.forEach(function (r) {
        const finished = new Date();
        finished.setDate(finished.getDate() - r[0]);
        finished.setMinutes(finished.getMinutes() - (5 + ((r[0] * 37) % 50)));
        records.push(mkRecord(stu, fmtDateTime(finished), r[1]));
      });
    }
    add('2024001', [
      [0,  [8.9, 18.4, 28.0, 37.5]],   // 92.8 一级乙等
      [6,  [8.4, 17.9, 27.3, 36.1]],   // 89.7 二级甲等
      [13, [8.2, 17.4, 26.8, 34.9]],   // 87.3 二级甲等
      [28, [7.8, 16.6, 25.5, 33.0]],   // 82.9 二级乙等
      [45, [8.0, 16.0, 24.6, 32.2]],   // 80.8 二级乙等
      [70, [7.2, 15.3, 23.8, 30.9]]    // 77.2 三级甲等
    ]);
    add('2024002', [
      [2,  [8.8, 18.1, 27.5, 35.8]],   // 90.2 二级甲等
      [21, [8.1, 17.0, 26.4, 33.6]],   // 85.1 二级乙等
      [55, [7.6, 15.5, 24.2, 30.8]]    // 78.1 三级甲等
    ]);
    add('2024003', [
      [4,  [8.6, 17.2, 26.0, 33.9]],   // 85.7 二级乙等
      [33, [7.5, 15.9, 24.8, 31.4]]    // 79.6 三级甲等
    ]);
    add('2024004', [[7, [9.1, 18.7, 28.6, 37.9]]]);  // 94.3 一级乙等
    add('2024005', [
      [9,  [8.3, 17.7, 26.9, 35.2]],   // 88.1 二级甲等
      [40, [7.9, 16.4, 25.3, 32.8]]    // 82.4 二级乙等
    ]);
    return records;
  }

  function users() { return loadJson(LS_USERS, null, seedUsers); }
  function saveUsers(list) { saveJson(LS_USERS, null, list); }
  function questions() { return loadJson(LS_QUESTIONS, null, seedQuestions); }
  function saveQuestions(list) { saveJson(LS_QUESTIONS, null, list); }
  function records() { return loadJson(LS_RECORDS, SS_RECORDS, seedRecords); }
  function saveRecords(list) { saveJson(LS_RECORDS, SS_RECORDS, list); }

  /** 时间倒序比较（用于最近成绩列表） */
  function byFinishedDesc(a, b) {
    return String(b.finished_at || '').localeCompare(String(a.finished_at || ''));
  }

  /** 当前登录用户：Mock 会话存在 sessionStorage，跨页面导航不丢失 */
  function currentUser() {
    return parseJson(storeGet(window.sessionStorage, SS_SESSION), null);
  }
  function saveSession(user) {
    storeSet(window.sessionStorage, SS_SESSION, JSON.stringify(user));
  }
  function clearSession() {
    storeRemove(window.sessionStorage, SS_SESSION);
  }  /* ===================== 3. 登录校验 ===================== */
  /** 每个"需要登录"的页面进来先调用一次：没登录会被跳到登录页 */
  function requireLogin(requiredRole) {
    const user = currentUser();
    if (!user) {
      window.location.replace(loginPageUrl());
      return null;
    }
    if (requiredRole && user.role !== requiredRole) {
      // 角色和当前区域不符（比如学生打开了管理页），送回属于他的首页
      const prefix = (isInside('student') || isInside('admin')) ? '../' : '';
      const home = prefix + (user.role === 'ADMIN' ? 'admin/dashboard.html' : 'student/dashboard.html');
      window.location.replace(home);
      return null;
    }
    return user;
  }

  /** 把登录用户信息填到导航栏（HTML 元素上加 data-user-name / data-user-no） */
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
    // 退出登录：清掉本地 Mock 会话，再回登录页
    $$('[data-action="logout"]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (!confirm('确定要退出登录吗？')) return;
        clearSession();
        window.location.replace(loginPageUrl());
      });
    });

    // 导出当前表格为 CSV（Excel 可直接打开）
    $$('[data-action="export"]').forEach(function (btn) {
      btn.addEventListener('click', function () { exportTableCsv(btn); });
    });
  }

  function exportTableCsv(btn) {
    // 兼容按钮在表头（与 table 相邻而不是祖先）的情况
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
    const csv = '\ufeff' + rows.join('\r\n');   // \ufeff 让 Excel 正确识别 UTF-8 中文
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    a.download = (document.title || 'export') + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  /* ============================================================
   * 5. 登录 / 注册页（login.html）—— Mock 账号校验
   * ============================================================ */
  function initLoginPage() {
    const loginMsg = byId('loginMsg');

    function showMsg(kind, text) {
      if (!loginMsg) return;
      loginMsg.className = 'alert alert-' + kind + ' py-2 small';
      loginMsg.innerHTML = text;
      loginMsg.classList.remove('d-none');
    }
    function hideMsg() { if (loginMsg) loginMsg.classList.add('d-none'); }

    // ---------- 登录 ----------
    const formLogin = byId('formLogin');
    if (formLogin) {
      formLogin.addEventListener('submit', function (e) {
        e.preventDefault();
        hideMsg();
        const username = (byId('loginName').value || '').trim();
        const password = byId('loginPwd').value;
        if (!username || !password) { showMsg('danger', '请输入账号和密码'); return; }

        const userList = users();
        let found = null;
        for (let i = 0; i < userList.length; i++) {
          if (userList[i].username === username) { found = userList[i]; break; }
        }
        if (!found || found.password !== password) {
          showMsg('danger', '账号或密码错误，请使用演示账号登录');
          return;
        }
        saveSession({ username: found.username, name: found.name, role: found.role });
        // 跳转目标由角色决定：管理员 -> 管理端，否则 -> 学生端
        window.location.href = (found.role === 'ADMIN') ? 'admin/dashboard.html' : 'student/dashboard.html';
      });
    }

    // 演示账号快捷填充（点击自动填入，方便测试）
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

    // ---------- 注册（只开放给学生，写入本地 Mock 账号库） ----------
    const formRegister = byId('formRegister');
    if (formRegister) {
      formRegister.addEventListener('submit', function (e) {
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

        const userList = users();
        const dup = userList.some(function (u) { return u.username === studentNo; });
        if (dup) { showMsg('danger', '该学号已被注册，请直接登录'); return; }

        userList.push({
          username: studentNo,
          password: pwd,
          name: name,
          role: 'STUDENT',
          student_no: studentNo,
          class_name: className
        });
        saveUsers(userList);
        byId('loginName').value = studentNo;   // 顺手帮你填好学号
        byId('loginPwd').value = '';
        switchTab('loginTab');
        showMsg('success', '注册成功，请用学号 <b>' + esc(studentNo) + '</b> 登录');
      });
    }
  }

  /* ============================================================
   * 6. 学生端：我的考试首页（student/dashboard.html）
   * ============================================================ */
  function myFinishedRecords(studentNo) {
    return records()
      .filter(function (r) { return r.student_no === studentNo && r.status === 'FINISHED'; })
      .sort(byFinishedDesc);
  }

  function avgOf(list) {
    if (!list.length) return 0;
    return round1(list.reduce(function (s, r) { return s + r.total_score; }, 0) / list.length);
  }
  function maxOf(list) {
    return list.reduce(function (m, r) { return Math.max(m, r.total_score); }, 0);
  }
  function minOf(list) {
    return list.reduce(function (m, r) { return Math.min(m, r.total_score); }, 100);
  }

  function initStudentDashboard() {
    const user = requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);
    setText('hiName', '你好，' + user.name + '同学');
    setText('bannerNo', '学号 ' + user.username);

    const mine = myFinishedRecords(user.username);
    const examCount = mine.length;
    const latest = mine[0] || null;

    setText('statExamCount', examCount);
    setText('statAvgScore', examCount ? fmtScore(avgOf(mine)) : '--');
    setText('statMaxScore', examCount ? fmtScore(maxOf(mine)) : '--');
    setText('statCurrentLevel', examCount ? (latest.level || '--') : '--');
    setHtml('headerLevel', examCount ? levelBadgeHtml(latest.level) : '<span class="badge text-bg-light">未定级</span>');

    const recent = mine.slice(0, 5);
    const box = byId('recentList');
    if (box) {
      if (!recent.length) {
        box.innerHTML = '<li class="list-group-item text-secondary small">还没有考试记录，点击上方按钮考一场吧</li>';
      } else {
        box.innerHTML = recent.map(function (item) {
          return '<a class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" href="report.html?record_id=' + item.record_id + '">' +
            '<span class="small">' + esc(shortDate(item.finished_at)) + '</span>' +
            '<span><span class="fw-bold text-success-score me-2">' + fmtScore(item.total_score) + ' 分</span>' +
            levelBadgeHtml(item.level) + '</span></a>';
        }).join('');
      }
    }
  }

  /* ============================================================
   * 7. 学生端：历史成绩 + 折线图（student/history.html）
   * ============================================================ */
  function initHistoryPage() {
    const user = requireLogin('STUDENT');
    if (!user) return;
    const all = myFinishedRecords(user.username);
    const asc = all.slice().reverse();                 // 时间升序 -> 画曲线
    const desc = all;                                  // 时间倒序 -> 表格

    const count = all.length;
    setText('statCount', count);
    setText('statMax', count ? fmtScore(maxOf(all)) : '--');
    setText('statMin', count ? fmtScore(minOf(all)) : '--');
    setText('statAvg', count ? fmtScore(avgOf(all)) : '--');

    const emptyTip = byId('chartEmpty');
    if (count === 0) {
      if (emptyTip) emptyTip.classList.remove('d-none');
    } else {
      drawScoreLine(byId('scoreChart'),
        asc.map(function (r) { return r.finished_at; }),
        asc.map(function (r) { return r.total_score; }));
    }

    renderHistoryTable(desc);
  }

  /** ECharts 折线图：历次总分 */
  function drawScoreLine(el, dates, scores) {
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    const minVal = Math.min.apply(null, scores);
    const maxVal = Math.max.apply(null, scores);
    const yMin = Math.max(0, Math.floor((minVal - 3) / 10) * 10);
    const yMax = Math.min(100, Math.ceil((maxVal + 3) / 10) * 10);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 30, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: dates.map(function (d) { return d.slice(5); }), axisLine: { lineStyle: { color: '#cbd5e1' } } },
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
        '<td><a class="btn btn-sm btn-outline-primary" href="report.html?record_id=' + rec.record_id + '">查看</a></td>' +
        '</tr>';
    }).join('');
  }

  /* ============================================================
   * 8. 学生端：成绩报告（student/report.html）
   * ============================================================ */
  function initReportPage() {
    const user = requireLogin('STUDENT');
    if (!user) return;

    let recordId = queryParam('record_id') || queryParam('recordId');
    let report = null;
    if (recordId) {
      const all = records();
      for (let i = 0; i < all.length; i++) {
        if (all[i].record_id === recordId) { report = all[i]; break; }
      }
    }
    if (!report) {
      // URL 没带 id 或找不到：默认取当前学生最近一次成绩
      report = myFinishedRecords(user.username)[0] || null;
    }
    if (!report) {
      setHtml('reportEmpty', '<div class="text-center py-5"><i class="bi bi-inbox fs-1 text-secondary"></i><p class="mt-3 text-secondary">还没有考试记录</p><a class="btn btn-primary" href="exam.html">去考一场</a></div>');
      const content = byId('reportContent'); if (content) content.classList.add('d-none');
      return;
    }
    renderReport(report, user);
  }

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
  }  /* ============================================================
   * 9. 学生端：考试页（student/exam.html）
   *    本地组卷 -> 逐题模拟录音 -> 前端评分 -> 交卷生成成绩记录
   * ============================================================ */
  const EXAM_SESSION_KEY = 'pthcs_exam_session';
  const EXAM_PASSAGE = '北京的秋天是美丽而宁静的。天很高很蓝，云很白很轻；路旁的梧桐树叶子渐渐变黄，一阵风吹过，金黄的叶片便轻轻飘落，铺成一条软软的地毯。公园里的人们放慢了脚步，有人坐在长椅上读书，有人在湖边散步，孩子们在空地上追着风筝跑。老北京人说，秋天是一年中最好的季节。清晨的胡同里，豆浆和油条的香味在微凉的风中飘散；傍晚时分，夕阳把城墙的影子拉得很长很长。我喜欢这样的秋天，喜欢它带给人的那种从容与温暖。不论走到哪里，只要想起故乡的秋天，心里就会涌起一阵亲切的感动。秋天教会我们欣赏平淡的生活，也让我们懂得珍惜身边的每一份美好。';

  let examState = null;           // 本次考试页面状态（不进 sessionStorage）
  let examTimer = null;           // 整场倒计时
  let mediaRecorder = null;
  let audioChunks = [];
  let recTimer = null;
  let recSeconds = 0;
  let finishAfterSubmit = false;  // 时间到时：提交完本题立即交卷

  /** 考试进度存在 sessionStorage：跨页面(type=1..4)切换不丢失 */
  function loadExamSession() {
    try { return JSON.parse(sessionStorage.getItem(EXAM_SESSION_KEY)) || null; }
    catch (e) { return null; }
  }
  function saveExamSession(sess) {
    sessionStorage.setItem(EXAM_SESSION_KEY, JSON.stringify(sess));
  }
  function clearExamSession() { sessionStorage.removeItem(EXAM_SESSION_KEY); }

  function isTypeDone(sess, type) {
    return !!(sess && sess.results && sess.results[type]);
  }
  /** 还有哪些题没提交 */
  function pendingTypes(paper, sess) {
    return paper.sections.filter(function (s) { return !isTypeDone(sess, s.type); });
  }
  /** 当前题之后第一个没提交的题；若后面没有，就绕回最前面的未提交题 */
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

  /** 内置 Mock 组卷：内容固定、每题限时与题量与真实考试一致 */
  function buildPaper() {
    return {
      record_id: 'rec_' + Date.now(),
      duration_seconds: 780,
      sections: [
        { type: 1, title: SECTION_TITLES[1], limit_text: '3分30秒', count_text: '10个', tip: '请大声清晰地朗读下列汉字，注意声母、韵母与声调。', items: ['爱', '白', '春', '风', '好', '民', '山', '水', '雪', '云'] },
        { type: 2, title: SECTION_TITLES[2], limit_text: '2分30秒', count_text: '10个', tip: '请朗读下列词语，注意轻声、儿化与词调。', items: ['人民', '朋友', '孩子', '花儿', '老师', '聪明', '时候', '知道', '热闹', '漂亮'] },
        { type: 3, title: SECTION_TITLES[3], limit_text: '4分钟', count_text: '1篇', tip: '请朗读下面的短文，注意停顿、语速与感情色彩。', items: [EXAM_PASSAGE] },
        { type: 4, title: SECTION_TITLES[4], limit_text: '3分钟', count_text: '1题', tip: '请围绕话题连贯地说三分钟左右，条理清楚、语句流畅。', items: ['我喜欢的季节'] }
      ]
    };
  }

  function initExamPage() {
    const user = requireLogin('STUDENT');
    if (!user) return;
    fillStudentBar(user);
    setText('stuName', user.name);
    setText('stuNo', user.username);

    // 同一场未交卷的考试：反复进入都继续同一份试卷（record_id 保持一致）
    let sess = loadExamSession();
    const paper = buildPaper();
    if (sess && sess.record_id) {
      paper.record_id = sess.record_id;
    } else {
      sess = {
        record_id: paper.record_id,
        deadline: Date.now() + paper.duration_seconds * 1000,
        results: {}                 // { 1:{score,total,detail}, 2:{...}, ... }
      };
      saveExamSession(sess);
    }

    examState = {
      user: user,
      paper: paper,
      sess: sess,
      curType: resolveCurrentType(paper, sess),
      busy: false,          // 正在提交中
      finished: false       // 已交卷
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
        '<span><i class="bi ' + icon + ' me-2"></i>' + esc(TYPE_NAMES[s.type]) + '</span>' + right + '</a>';
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

  /* ---------- 中间反馈区（提交成功/失败都显示在这里） ---------- */
  function feedbackHtml(html, cls) {
    const wrap = byId('submitResult');
    if (wrap) wrap.innerHTML = html ? '<div class="alert ' + cls + ' text-start mt-3 mb-0">' + html + '</div>' : '';
  }

  /** 已提交某题之后的总结卡片 */
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
    if (finishBtn) finishBtn.addEventListener('click', doFinishExam);
  }

  /** 提交成功后的处理 */
  function showSubmitSuccess(res) {
    saveExamSession(examState.sess);      // results 已经写进 sess，存进 sessionStorage
    renderExamNav();
    feedbackHtml(summaryHtml(res, true), 'alert-success');

    const finishBtn = byId('btnFinishNow');
    if (finishBtn) finishBtn.addEventListener('click', doFinishExam);

    // 2.5 秒后自动进入下一题（或自动交卷），用户也可以点按钮抢先操作
    clearTimeout(examState.autoTimer);
    const pending = pendingTypes(examState.paper, examState.sess);
    examState.autoTimer = setTimeout(function () {
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

    // 清除旧监听，防止重复渲染时重复绑定
    startBtn.onclick = null;
    stopBtn.onclick = null;

    if (isTypeDone(examState.sess, examState.curType)) {
      // 本题已提交：只读展示
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

  /** 开始录音；麦克风不可用时自动用"模拟录音"（模拟评分阶段） */
  async function onStartRec() {
    if (!examState || examState.busy || isTypeDone(examState.sess, examState.curType)) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
      alert('当前浏览器不支持录音，将使用模拟录音提交本题（模拟评分阶段，不影响体验）。');
      await uploadSection();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
      alert('无法打开麦克风：' + (err.message || err) + '\n将改用模拟录音提交本题。');
      await uploadSection();
    }
  }

  /** MediaRecorder 停止后触发：模拟"正在上传评分"后提交 */
  function onRecorderStopped() {
    if (mediaRecorder && mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach(function (track) { track.stop(); });
    }
    uploadSection();
  }

  function onStopRec() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      setRecState('<span class="spinner-border spinner-border-sm me-1"></span>正在上传评分…');
      mediaRecorder.stop();
    }
  }  /** 由 record_id + 题型生成稳定的 ±4% 波动，让每次模拟得分略有差异 */
  function mockJitter(seedText, type) {
    const s = String(seedText || '');
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h * 31) + s.charCodeAt(i)) >>> 0;
    return ((h + type * 7) % 9) - 4;
  }

  /**
   * 提交当前题型：不再上传文件，直接用本地 Mock 引擎评分
   * （保留约 600ms 的"评分中"反馈，模拟真实提交的节奏）
   */
  async function uploadSection() {
    if (!examState || examState.busy) return;
    const type = examState.curType;
    examState.busy = true;
    const startBtn = byId('btnStartRec');
    const stopBtn = byId('btnStopRec');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
    feedbackHtml('<span class="spinner-border spinner-border-sm me-2"></span>正在提交并评分…', 'alert-secondary');

    try {
      await delay(600);
      const basePct = { 1: 86, 2: 89, 3: 91, 4: 88 }[type] || 86;
      const pct = Math.max(60, Math.min(98, basePct + mockJitter(examState.sess.record_id, type)));
      const total = TYPE_TOTAL[type] || 100;
      const score = round1(total * pct / 100);
      const result = {
        score: score,
        total: total,
        detail: sectionDetail(pct)
      };

      examState.sess.results[type] = {
        score: result.score,
        total: result.total,
        detail: result.detail
      };
      examState.busy = false;

      // 时间到场景：提交完本题后立刻交卷
      if (finishAfterSubmit) {
        finishAfterSubmit = false;
        doFinishExam();
        return;
      }
      showSubmitSuccess(result);
    } catch (err) {
      examState.busy = false;
      setRecState('<i class="bi bi-exclamation-triangle-fill text-danger me-1"></i>提交失败：' + esc(err.message));
      if (startBtn) startBtn.disabled = false;
      if (stopBtn) stopBtn.disabled = true;
      feedbackHtml('<i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>提交失败：' + esc(err.message) +
        '<div class="small text-secondary mt-1">纯前端演示版一般不会失败，请刷新页面重试。</div>', 'alert-danger');
    }
  }

  /* ---------- 整场倒计时 ---------- */
  function startGlobalClock() {
    const display = byId('examClock');
    const bar = byId('examProgress');
    clearInterval(examTimer);

    function tick() {
      const total = examState.paper.duration_seconds;
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
    } else if (!isTypeDone(examState.sess, type)) {
      alert('考试时间到！未作答的题目不计分，正在交卷…');
      doFinishExam();
    } else {
      alert('考试时间到！正在交卷…');
      doFinishExam();
    }
  }

  /** 交卷：本地计算总分和等级，写入 Mock 成绩库后跳成绩报告 */
  async function doFinishExam() {
    if (!examState || examState.finished) return;
    examState.finished = true;
    try {
      feedbackHtml('<span class="spinner-border spinner-border-sm me-2"></span>正在交卷并计算总分…', 'alert-secondary');
      await delay(500);
      const sessionUser = examState.user;
      const profile = profileOf(sessionUser.username) || {
        username: sessionUser.username,
        name: sessionUser.name || sessionUser.username,
        role: 'STUDENT',
        student_no: sessionUser.username,
        class_name: ''
      };
      const sectionScores = [1, 2, 3, 4].map(function (t) {
        const res = examState.sess.results[t];
        return res ? res.score : 0;   // 未作答题目计 0 分
      });
      const rec = mkRecord(profile, nowStr(), sectionScores);
      const all = records();
      all.push(rec);
      saveRecords(all);
      clearExamSession();                     // 清掉考试进度
      window.location.href = 'report.html?record_id=' + rec.record_id;
    } catch (err) {
      examState.finished = false;
      alert('交卷失败：' + err.message);
    }
  }

  /* ============================================================
   * 10. 管理端：控制台（admin/dashboard.html）
   * ============================================================ */
  function initAdminDashboard() {
    if (!requireLogin('ADMIN')) return;
    const stats = adminStats();

    setText('statStudents', (stats.student_count || 0).toLocaleString('zh-CN'));
    setText('statQuestions', (stats.question_count || 0).toLocaleString('zh-CN'));
    setText('statToday', (stats.today_exam_count || 0).toLocaleString('zh-CN'));
    setText('statAvg', stats.avg_score == null ? '--' : fmtScore(stats.avg_score));

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

  /** 由本地 Mock 成绩库实时汇总管理端控制台数据 */
  function adminStats() {
    const allRecords = records().filter(function (r) { return r.status === 'FINISHED'; });
    const today = nowStr().slice(0, 10);
    const total = allRecords.reduce(function (s, r) { return s + r.total_score; }, 0);

    let typeAverages = [];
    if (allRecords.length) {
      typeAverages = [1, 2, 3, 4].map(function (t) {
      let sum = 0, count = 0;
      allRecords.forEach(function (r) {
        const sec = r.sections && r.sections.find(function (s) { return s.type === t; });
        if (sec && sec.score !== null && sec.score !== undefined) { sum += sec.score; count++; }
      });
      return {
        type: t,
        name: TYPE_NAMES[t],
        avg: count ? round1(sum / count) : 0
      };
      });
    }

    return {
      student_count: users().filter(function (u) { return u.role === 'STUDENT'; }).length,
      question_count: questions().length,
      today_exam_count: allRecords.filter(function (r) { return (r.finished_at || '').slice(0, 10) === today; }).length,
      avg_score: allRecords.length ? round1(total / allRecords.length) : null,
      recent_exams: allRecords.slice().sort(byFinishedDesc).slice(0, 6),
      type_averages: typeAverages
    };
  }

  /** ECharts 柱状图：各题型得分率（得分/该题满分） */
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
      const total = TYPE_TOTAL[item.type] || 100;
      return {
        name: item.name,
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
  }  /* ============================================================
   * 11. 管理端：题库管理（admin/questions.html）
   *     分页 / 题型筛选 / 关键字搜索 / 增删改全部在前端本地完成
   * ============================================================ */
  const PAGE_SIZE = 10;
  let qState = { page: 1, total_pages: 1, total: 0, rows: [] };

  function initQuestionAdminPage() {
    if (!requireLogin('ADMIN')) return;

    const searchInput = byId('questionSearch');
    const btnSearch = byId('btnSearchQuestion');
    const typeFilter = byId('qTypeFilter');
    const pager = byId('questionPageNav');

    // 查询条件变化 -> 回到第 1 页重新查
    function reloadFirstPage() { gotoQuestions(1); }

    if (btnSearch) btnSearch.addEventListener('click', reloadFirstPage);
    if (searchInput) searchInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') reloadFirstPage(); });
    if (typeFilter) typeFilter.addEventListener('change', reloadFirstPage);
    if (pager) pager.addEventListener('click', function (e) {
      const a = e.target.closest('a[data-pg]');
      if (!a) return;
      e.preventDefault();
      gotoQuestions(Number(a.getAttribute('data-pg')));
    });

    // 新增题目
    const btnAdd = byId('btnAddQuestion');
    if (btnAdd) btnAdd.addEventListener('click', function () { openQuestionModal(null); });

    // 表格行内的编辑/删除按钮（事件委托，一次绑定即可）
    const body = byId('questionTbody');
    if (body) body.addEventListener('click', onQuestionRowClick);

    // 保存（新增 / 编辑共用）
    const form = byId('formQuestion');
    if (form) {
      form.addEventListener('submit', function (e) {
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
        const list = questions();
        if (id) {
          for (let i = 0; i < list.length; i++) {
            if (String(list[i].id) === String(id)) {
              list[i].type = payload.type;
              list[i].content = payload.content;
              list[i].answer = payload.answer;
              list[i].difficulty = payload.difficulty;
              list[i].updated_at = nowStr();
              break;
            }
          }
        } else {
          let maxId = 0;
          list.forEach(function (q) { if (q.id > maxId) maxId = q.id; });
          list.push({
            id: maxId + 1,
            type: payload.type,
            content: payload.content,
            answer: payload.answer,
            difficulty: payload.difficulty,
            updated_at: nowStr()
          });
        }
        saveQuestions(list);
        hideModal('questionModal');
        gotoQuestions(qState.page);
      });
    }

    // 上传 Excel 题库：纯前端版无法真正解析 Office 文件，演示为新增示例题
    const excelInput = byId('questionExcel');
    if (excelInput) {
      excelInput.addEventListener('change', function () {
        const file = excelInput.files && excelInput.files[0];
        if (!file) return;
        const label = byId('uploadLabel');
        if (label) label.textContent = file.name;
        const list = questions();
        let maxId = 0;
        list.forEach(function (q) { if (q.id > maxId) maxId = q.id; });
        [
          ['1', '港', 'gǎng', '简单'],
          ['2', '咖啡', 'kā fēi', '中等'],
          ['4', '一次难忘的旅行', '参考提纲：时间地点、同行的人、印象最深的事。', '中等']
        ].forEach(function (row) {
          list.push({ id: ++maxId, type: Number(row[0]), content: row[1], answer: row[2], difficulty: row[3], updated_at: nowStr() });
        });
        saveQuestions(list);
        alert('前端纯展示版不解析 Excel 文件内容，已自动新增 3 条示例题目演示导入效果。');
        excelInput.value = '';
        if (label) label.textContent = '上传题库 Excel';
        gotoQuestions(1);
      });
    }

    gotoQuestions(1);
  }

  function hideModal(id) {
    const modalEl = byId(id);
    if (modalEl && window.bootstrap) {
      const inst = bootstrap.Modal.getInstance(modalEl);
      if (inst) inst.hide();
    }
  }

  function gotoQuestions(page) {
    if (page < 1) return;
    const filterVal = byId('qTypeFilter') ? byId('qTypeFilter').value : '';
    const kw = byId('questionSearch') ? (byId('questionSearch').value || '').trim() : '';

    // 先筛选，再本地分页
    const filtered = questions().filter(function (q) {
      if (filterVal && String(q.type) !== String(filterVal)) return false;
      if (kw && (q.content || '').indexOf(kw) === -1 && (q.answer || '').indexOf(kw) === -1) return false;
      return true;
    });
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const safePage = Math.min(page, totalPages);
    qState.page = safePage;
    qState.total = filtered.length;
    qState.total_pages = totalPages;
    qState.rows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
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

  function onQuestionRowClick(e) {
    const editBtn = e.target.closest('[data-edit]');
    if (editBtn) {
      openQuestionModal(findQuestionInRows(editBtn.getAttribute('data-edit')));
      return;
    }
    const delBtn = e.target.closest('[data-del]');
    if (delBtn) {
      if (!confirm('确认删除该题目？删除后不可恢复。')) return;
      const list = questions().filter(function (q) { return String(q.id) !== String(delBtn.getAttribute('data-del')); });
      saveQuestions(list);
      // 如果删的是本页最后一条，就回退一页
      const target = (qState.rows.length === 1 && qState.page > 1) ? qState.page - 1 : qState.page;
      gotoQuestions(target);
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
  }  /* ============================================================
   * 12. 管理端：学生成绩管理（admin/students.html）
   * ============================================================ */
  let stuRows = [];

  function initStudentsAdminPage() {
    if (!requireLogin('ADMIN')) return;

    const searchInput = byId('studentSearch');
    const btnSearch = byId('btnSearchStudent');
    if (btnSearch) btnSearch.addEventListener('click', reloadStudents);
    if (searchInput) searchInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') reloadStudents(); });

    const body = byId('studentTbody');
    if (body) body.addEventListener('click', onStudentRowClick);

    reloadStudents();
  }

  /** 学生档案：学生账号 + 其最近一次考试成绩（本地实时汇总） */
  function studentProfiles() {
    return users()
      .filter(function (u) { return u.role === 'STUDENT'; })
      .map(function (u) {
        const mine = myFinishedRecords(u.student_no);
        const last = mine[0] || null;
        return {
          student_no: u.student_no,
          name: u.name,
          class_name: u.class_name || '',
          last_exam_time: last ? last.finished_at : null,
          total_score: last ? last.total_score : null,
          level: last ? last.level : ''
        };
      });
  }

  function reloadStudents() {
    const kw = byId('studentSearch') ? (byId('studentSearch').value || '').trim() : '';
    const profiles = studentProfiles().filter(function (s) {
      if (!kw) return true;
      return (s.student_no || '').indexOf(kw) !== -1 ||
        (s.name || '').indexOf(kw) !== -1 ||
        (s.class_name || '').indexOf(kw) !== -1;
    });
    stuRows = profiles;

    const body = byId('studentTbody');
    if (body) {
      body.innerHTML = stuRows.length ? stuRows.map(function (s) {
        return '<tr>' +
          '<td>' + esc(s.student_no || '-') + '</td>' +
          '<td>' + esc(s.name || '-') + '</td>' +
          '<td>' + esc(s.class_name || '-') + '</td>' +
          '<td class="text-secondary small">' + esc(s.last_exam_time ? shortDate(s.last_exam_time) : '-') + '</td>' +
          '<td class="fw-bold text-success-score">' + (s.total_score == null ? '-' : fmtScore(s.total_score)) + '</td>' +
          '<td>' + levelBadgeHtml(s.level) + '</td>' +
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
  function openRecordsModal(name, studentNo) {
    const modalEl = byId('recordsModal');
    if (!modalEl) return;

    const list = myFinishedRecords(studentNo);
    setText('recordsTitle', esc(name) + '（' + esc(studentNo) + '）的成绩记录');
    setText('recordsCount', '共 ' + list.length + ' 条记录');
    if (window.bootstrap) new bootstrap.Modal(modalEl).show();

    const body = byId('recordsTbody');
    if (body) {
      body.innerHTML = list.length ? list.map(function (r) {
        return '<tr>' +
          '<td>' + esc(r.finished_at || '') + '</td>' +
          '<td class="fw-bold text-success-score">' + fmtScore(r.total_score) + '</td>' +
          '<td>' + levelBadgeHtml(r.level) + '</td>' +
          '<td><button type="button" class="btn btn-sm btn-outline-primary" data-record-id="' + r.record_id + '" data-record-name="' + esc(r.student_name) + '" data-record-no="' + esc(r.student_no) + '" data-record-class="' + esc(r.class_name || '') + '"><i class="bi bi-eye me-1"></i>查看报告</button></td>' +
          '</tr>';
      }).join('') : '<tr><td colspan="4" class="text-center text-secondary small py-3">该学生还没有完成任何考试</td></tr>';

      // 给"查看报告"按钮绑定点击（元素刚生成，直接逐个绑）
      body.querySelectorAll('[data-record-id]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          openReportModal(
            btn.getAttribute('data-record-name'),
            btn.getAttribute('data-record-no'),
            btn.getAttribute('data-record-class'),
            btn.getAttribute('data-record-id')
          );
        });
      });
    }
  }

  /** 弹窗二：任意一场考试的完整报告（管理员视角） */
  function openReportModal(name, no, className, recordId) {
    const all = records();
    let report = null;
    for (let i = 0; i < all.length; i++) {
      if (all[i].record_id === recordId) { report = all[i]; break; }
    }
    if (!report) { alert('未找到该场考试记录'); return; }

    // 先关掉"记录列表"弹窗，再开"报告"弹窗
    const recordsModal = byId('recordsModal');
    if (recordsModal && window.bootstrap) {
      const inst = bootstrap.Modal.getInstance(recordsModal);
      if (inst) inst.hide();
    }

    const modalEl = byId('reportModal');
    if (!modalEl) return;

    setText('rpName', name || '-');
    setText('rpNo', no || '-');
    setText('rpClass', className || '-');
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
   * 13. 页面路由器：<body data-page="xxx"> 对应不同页面
   * ============================================================ */
  function runPage() {
    const page = document.body ? document.body.getAttribute('data-page') : '';
    if (!page) return;

    // 退出登录 / 导出按钮每个页面都可能出现，统一先绑好
    initCommonActions();

    try {
      if (page === 'login') { initLoginPage(); return; }
      if (page === 'student-dashboard') { initStudentDashboard(); return; }
      if (page === 'exam') { initExamPage(); return; }
      if (page === 'report') { initReportPage(); return; }
      if (page === 'history') { initHistoryPage(); return; }
      if (page === 'admin-dashboard') { initAdminDashboard(); return; }
      if (page === 'admin-questions') { initQuestionAdminPage(); return; }
      if (page === 'admin-students') { initStudentsAdminPage(); return; }
    } catch (err) {
      alert(err && err.message ? err.message : String(err));
    }
  }

  document.addEventListener('DOMContentLoaded', runPage);
})();