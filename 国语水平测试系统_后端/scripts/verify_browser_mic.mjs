/* 前端录音链路验证（Node + 无头 Edge + 虚拟麦克风）
 *
 * 为什么需要它：浏览器录音（麦克风 -> 解码重采样成 16k PCM -> 上传 -> 讯飞出分）
 * 这条链路自动化接口测试覆盖不到，而它恰恰最容易出问题（采样率、格式、转码）。
 *
 * 用法（需本机已装 Node 与 Edge，且后端已启动）：
 *     node scripts\verify_browser_mic.mjs
 * 注意：
 *   - 会用虚拟麦克风（一段蜂鸣音）录音 6 秒并提交，讯飞会判"没有检测到有效朗读语音"，
 *     这是**预期结果**：它证明转码与上传链路是通的；
 *   - 每次运行都会给演示账号 2024001 建一条考试记录，跑完记得清掉。
 */// 用无头 Edge + 虚拟麦克风，真跑一遍"点击录音 -> 转码 -> 上传 -> 出分"的前端链路。
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = 'http://127.0.0.1:8080';
const PORT = 9333;
const TMP = process.env.TEMP || 'C:\\Windows\\Temp';

const child = spawn(EDGE, [
  '--headless=new',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${TMP}\\edge-mic-test-${Date.now()}`,
  '--use-fake-device-for-media-stream',
  '--use-fake-ui-for-media-stream',
  '--autoplay-policy=no-user-gesture-required',
  '--no-first-run', '--no-default-browser-check', '--disable-gpu',
  '--disable-features=Translate',
  BASE + '/login.html',
], { stdio: 'ignore' });

let target = null;
for (let i = 0; i < 40 && !target; i++) {
  await sleep(500);
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    target = list.find((t) => t.type === 'page' && t.url.startsWith(BASE));
  } catch { /* 还没起来 */ }
}
if (!target) {
  child.kill();
  console.error('连不上 Edge DevTools');
  process.exit(2);
}
console.log('已连上无头 Edge：', target.url);

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let seq = 0;
const pending = new Map();
const consoleErrors = [];
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    return;
  }
  if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description ?? '').join(' '));
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    consoleErrors.push('未捕获异常：' + (msg.params.exceptionDetails?.exception?.description || ''));
  }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params }));
});
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) {
    throw new Error('页面脚本异常：' + (r.exceptionDetails.exception?.description || JSON.stringify(r.exceptionDetails)));
  }
  return r.result.value;
}

await send('Runtime.enable');
await send('Page.enable');

// 等页面真正加载到本站点（刚连上时可能是 about:blank）
for (let i = 0; i < 40; i++) {
  const href = await evaluate('String(document.location.href)').catch(() => '');
  if (href && href.startsWith(BASE)) break;
  await sleep(500);
}
console.log('当前页面：', await evaluate('String(document.location.href)'));

const login = await evaluate(`(async () => {
  const r = await fetch(location.origin + '/api/auth/login', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: '2024001', password: '123456' })
  });
  const body = await r.json();
  return { code: body.code, name: body.data && body.data.name };
})()`);
console.log('1) 登录：', JSON.stringify(login));

await send('Page.navigate', { url: BASE + '/student/exam.html?type=1' });
await sleep(4500);
console.log('2) 考试页：', await evaluate(`JSON.stringify({
  title: (document.getElementById('examTitle') || {}).textContent,
  navItems: document.getElementById('examNav').children.length,
  startDisabled: document.getElementById('btnStartRec').disabled,
  questions: (document.getElementById('questionBox') || {}).textContent.slice(0, 30)
})`));

const flow = await evaluate(`(async () => {
  const log = [];
  const $ = (id) => document.getElementById(id);
  const start = $('btnStartRec'), stop = $('btnStopRec');
  log.push('点击"开始录音"');
  start.click();
  await new Promise((r) => setTimeout(r, 1500));
  log.push('  1.5s 后 recState = ' + $('recState').textContent.trim());
  await new Promise((r) => setTimeout(r, 5000));
  log.push('  6.5s 后 recState = ' + $('recState').textContent.trim() + ' / 停止按钮可用=' + !stop.disabled);
  if (stop.disabled) { log.push('!! 录音没起来，停止按钮不可用'); return log.join('\\n'); }
  log.push('点击"停止并提交"');
  stop.click();
  const marks = ['得分', '失败', '异常', '重录', '没有采集', '已提交'];
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const text = ($('submitResult').textContent || '') + ' ' + ($('recState').textContent || '');
    if (marks.some((m) => text.indexOf(m) >= 0)) { log.push('  ' + (i + 1) + 's 后拿到结果'); break; }
  }
  log.push('--- submitResult ---');
  log.push(($('submitResult').textContent || '').trim().replace(/\\s+/g, ' '));
  log.push('--- recState ---');
  log.push(($('recState').textContent || '').trim());
  return log.join('\\n');
})()`);
console.log('3) 录音流程：\n' + flow);
console.log('4) 页面 console 错误：', consoleErrors.length ? consoleErrors.slice(0, 5).join(' || ') : '（无）');

ws.close();
child.kill();
process.exit(0);