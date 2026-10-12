# 国语水平测试系统 · 后端（Python + MySQL）

把原来为 Java 后端写的前端页面，接到一套 **Python(FastAPI) + MySQL** 的真实后端上。
前端静态页面由本服务直接托管，启动后打开 <http://127.0.0.1:8080/> 即可使用。

- 后端代码目录：`<项目根>\国语水平测试系统_后端`
- 前端页面目录：`<项目根>`（由后端 `StaticFiles` 托管）
- 接口文档（自动生成）：<http://127.0.0.1:8080/api/docs>

---

## 一、环境要求

| 组件 | 版本 | 本机路径 |
| --- | --- | --- |
| Python | 3.10+（本机 3.13.15） | `D:\develop\Python\python.exe` |
| MySQL | 8.0+（本机 9.7.1） | `D:\DateBase\mysql-9.7.1-winx64` |

数据库：`guoyu_test`（utf8mb4），账号 `root` / `1234`。

---

## 二、快速开始

```powershell
# 1. 进入后端目录
cd "<项目根>\国语水平测试系统_后端"

# 2. 创建并激活虚拟环境（已建好可跳过）
D:\develop\Python\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 安装依赖（国内用清华源更快）
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 复制配置模板并填好数据库密码
Copy-Item .env.example .env

# 5. 启动
.\.venv\Scripts\python.exe run.py
```

启动成功后终端会打印：

```
正在启动 国语水平测试系统 ...
数据库连接：正常
服务地址：http://127.0.0.1:8080/  接口文档：/api/docs
前端静态目录：<项目根>
```

浏览器打开 <http://127.0.0.1:8080/> 即可。

### 演示账号

| 角色 | 账号 | 密码 |
| --- | --- | --- |
| 管理员 | `admin` | `admin123` |
| 学生 | `2024001` ~ `2024005` | `123456` |

首次启动会自动补演示账号、示例题库；若考试成绩表为空（或某个演示学生还没有成绩），还会生成一批演示成绩，让统计图表有内容可看。
把 `.env` 里的 `SEED_DEMO_DATA` 改成 `false` 即可关闭。

---

## 三、自检与维护脚本

```powershell
# 单元测试：不依赖数据库、不联网，随手就能跑（需先装 requirements-dev.txt）
.\.venv\Scripts\python.exe -m pytest

# 接口冒烟测试：把登录、考试、评分、交卷、成绩报告、题库增删改查全跑一遍
.\.venv\Scripts\python.exe scripts\smoke_test.py

# 考试闭环专项验证：超时自动交卷 / 重考上限 / 重复提交 / 上传上限 / 录音清理
.\.venv\Scripts\python.exe scripts\verify_exam_guards.py

# 安全加固专项验证：登录锁定 / 注册限流 / 安全响应头 / 文档开关 / 真实客户端 IP
.\.venv\Scripts\python.exe scripts\verify_hardening.py

# 生产环境账号维护（第 10 步）：改密码 / 清掉演示账号
.\.venv\Scripts\python.exe scripts\set_password.py --username admin --password "新的强密码"
.\.venv\Scripts\python.exe scripts\set_password.py --drop-demo-students          # 先预演，不删
.\.venv\Scripts\python.exe scripts\set_password.py --drop-demo-students --yes    # 确认后真删

# 重建演示成绩（会先清空考试记录，需显式确认）
.\.venv\Scripts\python.exe scripts\reset_demo_data.py --yes
```

冒烟测试需要后端已在运行。全部通过时最后会打印 `通过 N 项，失败 0 项`。

`verify_exam_guards.py` 会连数据库，自己建一个 `guard_probe` 测试账号、跑完再删掉，
不需要人工清理；它用模拟评分，不消耗讯飞额度。

---

## 四、目录结构

```
国语水平测试系统_后端/
├── .env / .env.example      # 环境变量（.env 含密码，已被 .gitignore 忽略）
├── .env.production.example  # 生产环境配置模板（第 10 步）
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 开发/测试依赖（pytest，第 9 步引入）
├── pytest.ini               # pytest 配置
├── run.py                   # 开发启动脚本
├── README.md
├── app/
│   ├── main.py              # FastAPI 入口：注册路由 + 托管前端 + 静态资源保护
│   ├── core/                # 配置 / 统一响应 / 异常 / 安全 / 常量 / 等级
│   ├── db/                  # 引擎与会话 / ORM 基类 / 种子数据
│   ├── models/              # 4 张表的 ORM 模型
│   ├── schemas/             # 请求体校验模型
│   ├── api/                 # 路由：health / auth / student / exam / admin
│   └── services/            # 业务逻辑 + 评分适配层（mock / ise）+ 录音清理
├── tests/                   # pytest 单元测试（不依赖数据库）
├── deploy/                  # 生产部署：nginx.conf / guoyu.service / DEPLOY.md
├── scripts/                 # 冒烟测试、专项验证、账号维护、演示数据重建
└── data/
    ├── uploads/             # 考生录音（按 记录号_题型_时间戳 命名）
    └── backup/              # 数据库备份
```

---

## 五、配置说明（.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_HOST` / `APP_PORT` | 监听地址与端口 | `0.0.0.0` / `8080` |
| `DEBUG` | 开启热重载 | `true` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL 连接 | `127.0.0.1:3306 root/1234 guoyu_test` |
| `SESSION_SECRET_KEY` | 会话 Cookie 签名密钥，**上线前必须换成随机串** | 随机生成 |
| `SESSION_MAX_AGE` | 会话有效期（秒） | `86400`（1 天） |
| `FRONTEND_DIR` | 前端静态页面目录 | 后端目录的上一级 |
| `UPLOAD_DIR` | 录音存放目录 | `data/uploads` |
| `SCORING_MODE` | `mock` 模拟评分 / `ise` 讯飞评测 | `mock` |
| `ISE_APP_ID` / `ISE_API_KEY` / `ISE_API_SECRET` | 讯飞开放平台参数 | 空 |
| `SEED_DEMO_DATA` | 首次启动是否生成演示成绩 | `true` |
| `EXAM_DURATION_SECONDS` | 整场考试时长（秒），同时下发给前端做倒计时 | `780` |
| `EXAM_DEADLINE_GRACE_SECONDS` | 交卷宽限期（秒），容忍正在路上的提交 | `30` |
| `MAX_EXAM_ATTEMPTS` | 单个学生可完成的考试场次上限，`0` = 不限 | `0` |
| `UPLOAD_RETENTION_DAYS` | 录音保留天数，`0` = 永久保留 | `14` |
| `MAX_UPLOAD_BYTES` | 单次录音上传大小上限（字节） | `20971520`（20MB） |
| `ENABLE_DOCS` | 是否开放 `/api/docs` 在线文档，**公网必须 false** | `true` |
| `CORS_ORIGINS` | 允许跨域的来源（逗号分隔），留空只放行本机 | 空 |
| `SESSION_COOKIE_SECURE` | 会话 Cookie 只走 HTTPS，配好证书后改 true | `false` |
| `SECURITY_HEADERS` | 是否追加安全响应头 | `true` |
| `LOGIN_MAX_FAILURES` | 同一账号窗口内失败几次就锁 | `5` |
| `LOGIN_MAX_IP_FAILURES` | 同一 IP 窗口内失败几次就锁（`0` = 关闭） | `100` |
| `LOGIN_WINDOW_SECONDS` | 登录失败统计窗口 = 锁定时长（秒） | `900` |
| `REGISTER_MAX_PER_HOUR` | 同一 IP 每小时最多注册几个 | `5` |
| `ISE_MAX_CONCURRENCY` | 讯飞评测最大并发（官方约 50 路） | `30` |
| `ISE_MAX_WAIT_SECONDS` | 评测排队等待上限（秒） | `20` |

---

## 六、接口清单

所有接口统一返回 `{ code, message, data }`：
`code = 0` 成功；`401` 未登录（前端自动跳登录页）；`403` 角色不符；
`410` 本场考试已超时（服务端已自动交卷）；其他非 0 为业务失败，`message` 可直接展示给用户。

### 认证（Session Cookie）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录，成功后写入签名 Cookie |
| POST | `/api/auth/register` | 学生注册 |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 当前登录用户 |

### 学生端

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/student/dashboard` | 首页：考试次数 / 平均分 / 最高分 / 当前等级 / 最近 5 次 |
| POST | `/api/exam/start` | 随机组卷（有未交卷且未超时的考试则继续同一份） |
| POST | `/api/exam/submit` | 提交单题（multipart：`recordId` / `type` / `file`） |
| POST | `/api/exam/{recordId}/finish` | 交卷，算总分与等级 |
| GET | `/api/exam/records` | 历史成绩列表 |
| GET | `/api/exam/records/{recordId}` | 单次成绩报告 |
| GET | `/api/exam/chart` | 成绩曲线数据 |

### 管理端（需 ADMIN）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/admin/stats` | 控制台统计 |
| GET | `/api/admin/students` | 学生列表（含最近一次成绩），支持 `keyword` |
| GET | `/api/admin/students/{studentNo}/records` | 某学生的全部成绩 |
| GET | `/api/admin/exam-records` | 全部成绩（分页 + `keyword`） |
| GET | `/api/admin/exam-records/{recordId}` | 任意一场考试的报告 |
| GET | `/api/admin/questions` | 题库分页查询（`type` / `keyword` / `page` / `size`） |
| POST | `/api/admin/questions` | 新增题目 |
| PUT | `/api/admin/questions/{id}` | 编辑题目 |
| DELETE | `/api/admin/questions/{id}` | 删除题目 |
| POST | `/api/admin/questions/upload` | Excel 批量导入题库 |
| POST | `/api/admin/uploads/cleanup` | 手动清理过期录音（保留天数见 `UPLOAD_RETENTION_DAYS`） |

### 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务 + 数据库状态 + 各表行数 |
| GET | `/api/check` | 轻量探活 |

---

## 七、数据库表

| 表 | 说明 |
| --- | --- |
| `t_user` | 用户（学生 + 管理员，用 `role` 区分） |
| `t_question` | 题库（`type`：1 读单字 / 2 读词语 / 3 朗读短文 / 4 命题说话） |
| `t_exam_record` | 考试记录，`paper_json` 存组卷结果（定死后不会中途换题） |
| `t_exam_section_score` | 各题得分 + 声韵调详情 |

密码存储沿用 Java 版的加盐 SHA-256：`hex(SHA256(salt + 明文))`，
所以从原 Java 项目迁移过来的账号可以直接登录，无需重置密码。

等级标准：`≥97` 一级甲等 / `≥92` 一级乙等 / `≥87` 二级甲等 / `≥80` 二级乙等 / `≥70` 三级甲等 / `≥60` 三级乙等 / 其余不入级。

---

## 八、切换到讯飞语音评测

### 8.1 现状与配置

| 题型 | 评测引擎 |
| --- | --- |
| 1 读单字 | 讯飞 `read_syllable` |
| 2 读词语 | 讯飞 `read_word` |
| 3 朗读短文 | 讯飞 `read_chapter` |
| 4 命题说话 | 本地流利度评分（讯飞中文题型没有"自由说"） |

`.env` 里的相关配置：

```ini
SCORING_MODE=ise          # mock=全程模拟评分；ise=讯飞真实评测
ISE_APP_ID=...
ISE_API_KEY=...
ISE_API_SECRET=...
ISE_SEND_INTERVAL=0.01    # 音频帧间隔（秒），官方建议 0.04；实测 0.01 评分完全一致且快 4 倍
ISE_MAX_RETRY=2           # 网络失败重试次数（讯飞会偶发掐连接）
ISE_FALLBACK_MOCK=true    # 讯飞不可用时回退模拟分；正式部署建议改 false
```

**换 key 只改 `ISE_APP_ID` / `ISE_API_KEY` / `ISE_API_SECRET` 这三行再重启，不用改代码**
（个人 key 验证完换小组 key 就是这个流程）。

### 8.2 协议要点（文档没写清、实测踩出来的）

1. `business` 是**扁平**结构：没有 `data_type` 字段，也不要再套一层 `business`
   （套了服务端回 `10163 unknown field`）；
2. 首帧只传参数：`cmd="ssb"`、`data={"status":0}`，**这一帧不带音频**；
3. 音频帧必须带 `business.cmd="auw"` + `aus`：首帧 `1` / 中间 `2` / 末帧 `4`，
   `data.status` 对应 `1` / `1` / `2`；漏了 `cmd`/`aus` 会回 `30002`；
4. 返回 XML 的 `total_score` **本来就是百分制**（0~100），不要再乘 20；
5. 单字 / 词语题的参考文本要用**空格分隔**：50 个词（101 字）连成一串会被判
   `48195 试题格式错误`，空格分开就正常（见 `exam_service.SPACED_TYPES`）；
6. 中文题型只有 `read_syllable` / `read_word` / `read_sentence` / `read_chapter`，
   **没有"自由说"**（`read_recitation` 实测回 48195，那是要另买试卷定制服务的）。

### 8.3 声母 / 韵母 / 声调怎么来的

讯飞只给整句的 `phone_score`（声韵分）和 `tone_score`（调型分）。页面上的声韵调三个数
是从音素节点统计出来的（字段语义见官方"中文评测返回参数说明"）：

| 音素节点 | 判定为"对"的条件 |
| --- | --- |
| `phone[@is_yun="0"]`（声母） | `perr_msg="0"` |
| `phone[@is_yun="1"]`（韵母） | `perr_msg` 为 `0`（都对）或 `2`（只有调型错） |
| 声调 | `perr_msg` 为 `0` 或 `1`（调型对） |

没有 `is_yun` 属性的 `sil` / `silv` / `fil`（静音、噪声）节点会被跳过；
`is_rejected="true"`（引擎判定乱说）或 `except_info≠0` 时不出分，直接提示学生重录。

### 8.4 第四题为什么不用讯飞

讯飞 ISE 的中文题型只有字 / 词 / 句 / 篇章，"自由说"需要另外购买试卷定制服务。
所以第四题在本地评分（`app/services/scoring/free_speak.py`）：把录音切成 20ms 帧算能量做 VAD，
按 **有效说话时长 45% + 停顿密度/最长停顿 35% + 有效发音占比 20%** 折算成 0~100 分，
再按本题满分 40 折算。报告里 `detail.engine = "local_free_speak"`（讯飞的写 `xfyun_ise`）。

### 8.5 联调工具

```powershell
# 探协议：按官方 v2 协议发帧，把原始评测 XML 落到 data\ise_probe\
.venv\Scripts\python.exe scripts\ise_probe.py --category read_word --text 热爱 --audio data\samples\word.wav

# 端到端：登录 -> 组卷 -> 上传录音 -> 评分 -> 交卷 -> 报表
.venv\Scripts\python.exe scripts\ise_e2e_test.py --paper-out data\ise_probe\paper.json
.venv\Scripts\python.exe scripts\ise_e2e_test.py --record <试卷id> --audio 3=data\samples\word.wav --finish

# 到讯飞服务器的连通性诊断（区分本地网络问题与讯飞限流）
.venv\Scripts\python.exe scripts\ise_diag.py

# 前端录音链路（麦克风 -> 转码 -> 上传 -> 出分），需 Node + Edge
node scripts\verify_browser_mic.mjs
```

`data\samples\*.wav` 里留了几个 16k/16bit/单声道测试音频（系统 TTS 生成），
不用麦克风就能验证整条评分链路；`data\ise_probe\*.xml` 是真实返回的评测 XML，可用于对照解析逻辑。

---

## 九、考试闭环保护（第 9 步）

倒计时原先只在前端算：学生关掉浏览器，那场考试就会永远挂在 `IN_PROGRESS`，
下次进来还会接着考旧卷，等于无限加时。第 9 步把这些规则全部挪到了服务端。

| 配置项（.env） | 默认 | 作用 |
| --- | --- | --- |
| `EXAM_DURATION_SECONDS` | `780` | 整场考试时长，同时作为 `duration_seconds` 下发给前端 |
| `EXAM_DEADLINE_GRACE_SECONDS` | `30` | 交卷宽限期，容忍正在路上的请求 |
| `MAX_EXAM_ATTEMPTS` | `0`（不限） | 单个学生允许完成的场次上限 |
| `UPLOAD_RETENTION_DAYS` | `14`（`0` = 永久） | 录音保留天数 |
| `MAX_UPLOAD_BYTES` | `20971520`（20MB） | 单次录音上传大小上限 |

服务端具体做了五件事：

1. **权威超时**：硬截止时间 = 开始时间 + 时长 + 宽限。
   - `start_exam` 发现上一次考试已过期 → 先自动交卷结算，再开一场**全新的**考试；
   - `submit_section` 超过截止时间 → 拒绝本题、自动交卷，返回业务码 **`410`**（前端据此跳成绩页）；
   - 自动交卷的 `finished_at` 记成"真正到点的那一刻"（不含宽限），成绩单上的用时才准确。
2. **重考次数上限**：`MAX_EXAM_ATTEMPTS` 用满后 `start_exam` 返回 `400`；
   只统计 `FINISHED` 的记录，被超时自动交卷的那一场同样计入。
3. **重复提交只评分一次**：`submit_section` 对考试记录加 `SELECT ... FOR UPDATE` 行锁，
   同一题第二次提交直接返回首次成绩（多一个 `cached: true` 标记），不再调用讯飞，省一次计费。
4. **上传大小上限**：边读边判，超限返回 `400`，不会把超大请求整个读进内存。
5. **录音清理**：服务启动时自动跑一次，也可用 `POST /api/admin/uploads/cleanup` 手动触发；
   只删 `rec_*` 且超过保留期的文件，`UPLOAD_RETENTION_DAYS=0` 时**一个都不删**。

专项验证脚本（会连数据库，自建自删测试账号）：

```powershell
.\.venv\Scripts\python.exe scripts\verify_exam_guards.py
```

跑通会打印 12 项 `[PASS]`，覆盖超时自动交卷、超时提交被拒（410）、重考上限、
重复提交复用、上传上限、录音清理。

单元测试（`tests/`，44 项，不依赖数据库）：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 十、公网部署与安全加固（第 10 步）

完整部署步骤见 **`deploy/DEPLOY.md`**（服务器准备、nginx 配置、HTTPS 证书、
systemd 托管、上线自检命令、备份与回滚）。这里只说明这一版新增的安全能力。

### 10.1 新增的防护

| 防护 | 实现位置 | 配置 |
| --- | --- | --- |
| 登录失败锁定 | `app/services/login_guard.py` + `t_login_attempt` 表 | `LOGIN_MAX_FAILURES` / `LOGIN_MAX_IP_FAILURES` / `LOGIN_WINDOW_SECONDS` |
| 注册刷号 | 进程内滑动窗口限流 `app/core/limits.py` | `REGISTER_MAX_PER_HOUR` |
| 评测并发保护 | 并发闸门包住讯飞调用，排队超时返回 429 | `ISE_MAX_CONCURRENCY` / `ISE_MAX_WAIT_SECONDS` |
| 录音上传上限 | 边读边判，超限直接 400（第 9 步） | `MAX_UPLOAD_BYTES` |
| 接口文档开关 | 关掉 `docs_url` / `openapi_url` | `ENABLE_DOCS` |
| CORS 白名单 | 只放行显式配置的来源 | `CORS_ORIGINS` |
| 安全响应头 | 中间件统一追加 | `SECURITY_HEADERS` |
| 会话 Cookie | `HttpOnly` + `SameSite=Lax` + 可选 `Secure` | `SESSION_COOKIE_SECURE` |
| 默认弱口令告警 | 启动时检查并打 `WARNING` | —— |
| 前端离线化 | Bootstrap / Icons / ECharts 落到 `assets/vendor/` | —— |

### 10.2 上线前必须改的配置

```ini
DEBUG=false
ENABLE_DOCS=false
SEED_DEMO_DATA=false
SESSION_COOKIE_SECURE=true
SESSION_SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(48))">
DB_PASSWORD=<别再用 1234>
CORS_ORIGINS=<你的域名>
```

完整模板见 `.env.production.example`。演示账号（`admin/admin123`、学生 `123456`）
是随首次启动写入的，上线前用 `scripts/set_password.py` 改密码并清掉。

### 10.3 真实客户端 IP 是限流的前提

限流和登录锁定都按客户端 IP 计数。后端跑在 nginx 后面时**必须**这样启动：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080 \
    --proxy-headers --forwarded-allow-ips=127.0.0.1
```

否则 `request.client` 拿到的永远是 nginx 自己的地址，**一个人失败就会锁掉全校**。
`deploy/guoyu.service` 里已经带好这两个参数；nginx 侧要用
`$proxy_add_x_forwarded_for`（追加真实 IP），不要用 `$http_x_forwarded_for`。

### 10.4 多 worker 的注意事项

`REGISTER_MAX_PER_HOUR` 和 `ISE_MAX_CONCURRENCY` 是**进程内**计数，用 `--workers N`
时每个进程各算各的，等于把阈值放大 N 倍。建议 worker 控制在 1~2 个，
并把 `ISE_MAX_CONCURRENCY` 按 worker 数等比调小。

登录锁定不受影响：它走数据库计数，多 worker 下依然是全局的。

### 10.5 自检

```powershell
.\.venv\Scripts\python.exe -m pytest                     # 60 项单元测试（不连库）
.\.venv\Scripts\python.exe scripts\smoke_test.py         # 39 项接口冒烟
.\.venv\Scripts\python.exe scripts\verify_exam_guards.py # 12 项考试闭环
.\.venv\Scripts\python.exe scripts\verify_hardening.py   # 7 项安全加固
```

---

## 十一、常见坑（都在这台机器上踩过）

1. **代理导致装不上依赖**
   环境里有 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 指向 `127.0.0.1:7890`，代理没开时 pip 会报
   `WinError 10061`。先清掉代理再装：
   ```powershell
   $env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:ALL_PROXY=''
   $env:http_proxy=''; $env:https_proxy=''; $env:all_proxy=''; $env:NO_PROXY='*'
   ```

2. **MySQL 9 的 `caching_sha2_password`**
   MySQL 8+ 默认认证插件要求客户端具备加密能力，PyMySQL 必须配合 `cryptography` 才能连上。
   `requirements.txt` 已包含，别漏装。

3. **中文路径**
   PowerShell 里路径要加引号；`mysql.exe` 的 `SOURCE` 命令遇到中文路径会报语法错误，
   导 SQL 请用 `Get-Content ... | mysql` 之类的管道方式。

4. **端口被占用**
   `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8080)` —— 上一次的服务没退干净。先找到占用进程再启动：
   ```powershell
   Get-NetTCPConnection -LocalPort 8080 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
   ```

5. **前端页面能打开但接口全 401**
   前后端必须 **同源** 访问（都用 <http://127.0.0.1:8080/>）。
   直接双击 HTML 用 `file://` 打开，Cookie 和 `fetch('/api/...')` 都不会生效。

6. **后端目录不能被下载**
   前端目录与后端目录是父子关系，`app/main.py` 里加了中间件，`/国语水平测试系统_后端/**`、`/.env`、`/data/**` 一律返回 404，
   避免数据库密码和会话密钥被直接下载。改动静态目录结构时记得同步这段逻辑。

7. **控制台中文乱码**
   Windows 终端默认 GBK，Python 日志里的中文会花掉。启动前设 `$env:PYTHONIOENCODING='utf-8'`，或把终端切到 UTF-8。

8. **未作答的题按 0 分计**
   交卷时只统计已提交的题目，没提交的题目记 0 分，所以中途交卷总分和等级会偏低——这是预期行为。

9. **讯飞偶发掐连接（WinError 10053）**
   连续快速发起评测时服务端会直接断开，此时**继续发帧只会看到 10053，看不到真正的错误码**。
   `ise.py` 现在是"边发边读"，能在断开前把 `48195` / `30002` 这种关键报错读出来，
   并按 `ISE_MAX_RETRY` 退避重试。排查问题请先看后端日志里的讯飞错误码。

10. **`read_word` 参考文本必须分隔**
    50 个词连成一串会被判 `48195 试题格式错误`，用空格分开即可（`exam_service.SPACED_TYPES`）。

11. **录音必须是 16k/16bit/单声道**
    前端 `js/main.js` 的 `toIsePcm()` 已把 `MediaRecorder` 的 webm/opus 解码重采样后再上传，
    后端 `read_pcm()` 同时兼容裸 PCM 与 WAV。手工测试时别直接传 mp3/webm，会报
    `40007` / `10043 音频解码失败`。

12. **带麦克风真机验证**
    浏览器录音链路（麦克风 -> 转码 -> 上传 -> 出分）依赖真实设备，
    自动化脚本覆盖不到，发布前请用 Chrome/Edge 手动走一遍四道题。

---

## 十二、纯前端演示版（无后端）

前端提供了两套脚本：

- `js/main.js` —— 当前版本，走真实接口；
- `js/main.mock.js` —— 保留的纯 Mock 版，数据全部内置，**双击 HTML 就能预览全部界面**，不需要后端。

要把页面切回"无需后端"的演示模式，把 HTML 底部的

```html
<script src="../js/main.js"></script>
```

改成

```html
<script src="../js/main.mock.js"></script>
```

即可（`index.html` / `login.html` 是 `js/main.js`）。