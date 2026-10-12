# 国语水平测试系统 · 公网部署手册（第 10 步）

面向 Ubuntu 22.04 / 24.04（Rocky / Alma 见文末差异说明）。
整套流程约 40 分钟，命令可以逐段复制。

---

## 一、目标架构

```
                    公网
                     │ 443 (HTTPS)
                     ▼
        ┌──────────────────────────┐
        │  nginx                   │  限流 / HTTPS / 上传大小限制
        └────────────┬─────────────┘
                     │ 127.0.0.1:8080（不对外）
                     ▼
        ┌──────────────────────────┐
        │  uvicorn (FastAPI)       │  systemd: guoyu.service
        └────────────┬─────────────┘
                     │ 127.0.0.1:3306（不对外）
                     ▼
        ┌──────────────────────────┐
        │  MySQL 8                 │  库名 guoyu_test
        └──────────────────────────┘
```

三条底线：

1. **8080 和 3306 都只监听 127.0.0.1** —— 外网只能碰到 443；
2. **安全头、限流、HTTPS 由 nginx 兜第一层**，应用层再做账号锁定与并发闸门；
3. **后端目录绝不能放进前端目录** —— 否则 `.env`（含数据库密码）可能被直接下载。

---

## 二、上线前必须确认的 6 件事

| # | 项目 | 检查方式 |
| --- | --- | --- |
| 1 | `SEED_DEMO_DATA=false`，且演示账号已清理 | `python scripts/set_password.py --drop-demo-students` |
| 2 | `admin` 密码已改，不再是 `admin123` | `python scripts/set_password.py --username admin --password '...'` |
| 3 | `SESSION_SECRET_KEY` 是随机长串 | 见下方生成命令 |
| 4 | 数据库密码不是 `1234`，且 MySQL 不对公网开放 | `ss -lntp \| grep 3306` 应显示 `127.0.0.1:3306` |
| 5 | `.env` 只有 `guoyu` 用户能读 | `chmod 600 .env` |
| 6 | `ENABLE_DOCS=false`、`SESSION_COOKIE_SECURE=true` | 打开 `/api/docs` 应返回 404 |

> 服务启动时会在日志里打印弱口令告警（`⚠️ 安全检查：…`）。
> **日志里出现这行就说明还没上线合格**。

---

## 三、服务器准备（一次性）

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx mysql-server git

# 建一个专用系统用户，别用 root 跑服务
sudo useradd --system --create-home --shell /bin/bash guoyu
sudo mkdir -p /srv/guoyu/frontend /srv/guoyu/backend
sudo chown -R guoyu:guoyu /srv/guoyu
```

### 3.1 建库与专用数据库账号

```bash
sudo mysql
```

```sql
CREATE DATABASE guoyu_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'guoyu'@'127.0.0.1' IDENTIFIED BY '换成A-Za-z0-9的强密码';
GRANT ALL PRIVILEGES ON guoyu_test.* TO 'guoyu'@'127.0.0.1';
FLUSH PRIVILEGES;
EXIT;
```

确认 MySQL 只监听本机（默认就是）：

```bash
sudo ss -lntp | grep 3306        # 必须是 127.0.0.1:3306，不能是 0.0.0.0:3306
```

---

## 四、部署应用

### 4.1 上传代码

把 `frontend` 和 `backend` 作为**平级**目录放进去：

```
/srv/guoyu/
├── frontend/      # 前端静态页（index.html / login.html / student / admin / assets ...）
└── backend/       # 后端（app / scripts / deploy / requirements.txt ...）
```

```bash
# 本地打包后上传，或在服务器上 git clone
sudo -u guoyu rsync -av ./frontend/ /srv/guoyu/frontend/
sudo -u guoyu rsync -av ./国语水平测试系统_后端/ /srv/guoyu/backend/
```

> 前端目录名不改也行，但 `.env` 里的 `FRONTEND_DIR` 要写对。

### 4.2 装依赖

```bash
sudo -u guoyu python3 -m venv /srv/guoyu/backend/.venv
sudo -u guoyu /srv/guoyu/backend/.venv/bin/pip install -U pip
sudo -u guoyu /srv/guoyu/backend/.venv/bin/pip install \
    -r /srv/guoyu/backend/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.3 写配置

```bash
sudo -u guoyu cp /srv/guoyu/backend/.env.production.example /srv/guoyu/backend/.env
# 生成一个会话密钥，填进 SESSION_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
sudo -u guoyu nano /srv/guoyu/backend/.env
sudo chmod 600 /srv/guoyu/backend/.env
```

要改的 8 项：`DB_PASSWORD`、`SESSION_SECRET_KEY`、`FRONTEND_DIR`、`UPLOAD_DIR`、
`ISE_APP_ID/API_KEY/API_SECRET`、`SESSION_COOKIE_SECURE=true`、`ENABLE_DOCS=false`、
`SEED_DEMO_DATA=false`。

### 4.4 先手动跑一次，确认能起来

```bash
cd /srv/guoyu/backend
sudo -u guoyu .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

看到 `数据库连接：正常` 和 `Application startup complete` 就说明没问题，`Ctrl+C` 停掉。

### 4.5 配 systemd

```bash
sudo cp /srv/guoyu/backend/deploy/guoyu.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now guoyu
sudo systemctl status guoyu
```

### 4.6 改掉默认密码、清掉演示账号

```bash
cd /srv/guoyu/backend
sudo -u guoyu .venv/bin/python scripts/set_password.py --username admin --password '你的强密码'
sudo -u guoyu .venv/bin/python scripts/set_password.py --drop-demo-students    # 先预演
sudo -u guoyu .venv/bin/python scripts/set_password.py --drop-demo-students --yes
sudo systemctl restart guoyu
```

---

## 五、nginx + HTTPS

### 5.1 配站点

```bash
sudo cp /srv/guoyu/backend/deploy/nginx.conf /etc/nginx/conf.d/guoyu.conf
sudo nano /etc/nginx/conf.d/guoyu.conf     # 改 server_name 为你的域名
sudo nginx -t && sudo systemctl reload nginx
```

### 5.2 申请证书（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo mkdir -p /var/www/certbot
sudo certbot --nginx -d guoyu.example.com
sudo systemctl list-timers | grep certbot    # 自动续期是否已装好
```

证书就位后，把 `.env` 里的 `SESSION_COOKIE_SECURE` 改成 `true`，重启后端：

```bash
sudo systemctl restart guoyu
```

> 没有域名时可以用自签证书先测通，但浏览器会报不安全，正式使用必须用受信任证书。

### 5.3 云服务器安全组

只放行 **22 / 80 / 443**。**3306 和 8080 一律不要开放**。

---

## 六、上线自检（逐条过一遍）

```bash
# 1. 接口通不通
curl -s https://guoyu.example.com/api/health | head -c 300

# 2. 文档已关闭（应返回 404 或统一 JSON 的 404）
curl -s -o /dev/null -w '%{http_code}\n' https://guoyu.example.com/api/docs

# 3. 安全响应头在不在
curl -sI https://guoyu.example.com/login.html | grep -Ei 'strict-transport|x-content-type|x-frame|referrer'

# 4. Cookie 带 Secure 标记
curl -sI -X POST https://guoyu.example.com/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"错误密码"}' | grep -i set-cookie
#    （这条会记一次失败登录，正式环境别刷太多次）

# 5. 限流生效（连续打 30 次登录，应出现 429）
for i in $(seq 1 30); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST https://guoyu.example.com/api/auth/login \
       -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}'
done; echo
```

再手工走一遍：**管理员登录 → 学生登录 → 完整考一场 → 看成绩报告**。

---

## 七、日常运维

```bash
sudo systemctl status guoyu
sudo journalctl -u guoyu -f                # 实时日志
tail -f /srv/guoyu/backend/data/server.err.log
```

**备份**（建议加进 crontab，每天凌晨）：

```bash
mysqldump -u guoyu -p guoyu_test | gzip > /srv/guoyu/backend/data/backup/guoyu_$(date +%F).sql.gz
```

**录音清理**：服务每天启动时会按 `UPLOAD_RETENTION_DAYS`（默认 14 天）自动清，
也可以手动触发：

```bash
curl -X POST https://guoyu.example.com/api/admin/uploads/cleanup --cookie 'guoyu_session=...'
```

**更新版本**：

```bash
sudo systemctl stop guoyu
sudo -u guoyu rsync -av ./国语水平测试系统_后端/ /srv/guoyu/backend/
sudo -u guoyu /srv/guoyu/backend/.venv/bin/pip install -r /srv/guoyu/backend/requirements.txt
sudo systemctl start guoyu
```

**回滚**：代码目录保留上一版副本，替换回去再启动即可（数据库表结构没变，不用回滚数据）。

---

## 八、并发与容量

| 环节 | 上限 | 说明 |
| --- | --- | --- |
| 讯飞语音评测 | 官方约 **50 路并发** | 应用层用 `ISE_MAX_CONCURRENCY`（默认 30）排队；排不到会返回 429，让学生稍后重交本题 |
| 数据库连接池 | `pool_size=5 + overflow=10` | 每场考试 4 次提交，够几十人同时考试 |
| uvicorn worker | 建议 1~2 | **限流是进程内计数**，worker 越多阈值越松，务必同比调小 `ISE_MAX_CONCURRENCY` |
| 单次录音 | 20MB（`MAX_UPLOAD_BYTES`） | 命题说话 3 分钟约 5.8MB，余量充足 |

按 30 路并发、每题平均 4 秒估算，一小时大约能评 2.7 万次提交 —— 一次 40 人的
班级考试（40×4=160 次提交）完全无压力。

---

## 九、Rocky / Alma / CentOS 差异

```bash
sudo dnf install -y python3 python3-pip nginx mysql-server
sudo systemctl enable --now nginx mysqld
# SELinux 需要额外放行 nginx 访问后端端口：
sudo setsebool -P httpd_can_network_connect 1
# 防火墙
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload
```

配置文件路径改为 `/etc/nginx/conf.d/guoyu.conf`（同上），systemd 单元路径相同。

---

## 十、常见坑

1. **登录锁定误伤全校**：校园网常整栋楼共用一个出口 IP。
   如果日志里频繁出现 `IP x.x.x.x 登录失败次数达到上限`，把 `.env` 里的
   `LOGIN_MAX_IP_FAILURES` 调大（或设 `0` 关闭 IP 级锁定，保留账号级锁定）。
   改完 `sudo systemctl restart guoyu`。
2. **所有人被算成同一个 IP**：忘了给 uvicorn 加
   `--proxy-headers --forwarded-allow-ips=127.0.0.1`，或者 nginx 用了
   `$http_x_forwarded_for`（应改回 `$proxy_add_x_forwarded_for`）。
3. **上传报 413**：nginx 的 `client_max_body_size` 比后端上限小，改成 25m。
4. **评测超时**：讯飞单次最长 60s，nginx 的 `proxy_read_timeout` 要给到 120s。
5. **`.env` 泄漏**：后端目录放进前端目录里，且 nginx 直接托管前端。
   保持两者平级，并保留 `nginx.conf` 里那条 `location ^~ /国语水平测试系统_后端/` 兜底。
6. **录不上音**：浏览器麦克风权限要求 HTTPS（或 localhost）。
   用 http 访问公网域名时 `getUserMedia` 会直接失败。