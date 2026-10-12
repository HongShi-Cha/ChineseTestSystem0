r"""接口冒烟测试：把 7 步流程从头到尾跑一遍。

用法：
    cd 国语水平测试系统_后端
    .venv\\Scripts\\python.exe scripts\\smoke_test.py

需要先启动后端服务（python run.py）。
"""
import http.cookiejar
import json
import random
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote

BASE = "http://127.0.0.1:8080"

#: 给每次运行模拟一个独立的客户端 IP。
#: 后端跑在本机时 uvicorn 会信任来自 127.0.0.1 的 X-Forwarded-For（默认
#: --forwarded-allow-ips=127.0.0.1），这样反复跑冒烟测试就不会把第 10 步新加的
#: 注册限流 / 登录失败锁定给撞满，用例本身也就顺带验证了取真实 IP 的链路。
CLIENT_IP = "10.66.{}.{}".format(random.randint(1, 254), random.randint(1, 254))

PASSED = 0
FAILED = 0


def client() -> urllib.request.OpenerDirector:
    """带 Cookie 的请求器（模拟浏览器会话）。"""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(opener, method, path, payload=None, raw=None, content_type=None):
    # 中文查询参数必须百分号编码，否则 http.client 会因非 ASCII 报错
    url = BASE + quote(path, safe="/?&=%")
    data = None
    headers = {"X-Forwarded-For": CLIENT_IP}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    elif raw is not None:
        data = raw
        headers["Content-Type"] = content_type or "application/octet-stream"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - 便于排错
        return {"code": exc.code, "message": str(exc), "data": None}
    return json.loads(body)


def check(label, condition, extra=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [OK]   {label}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label} {extra}")


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """手工拼 multipart/form-data，避免依赖 requests。"""
    boundary = "----guoyu" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())
    for name, (filename, content) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(b"Content-Type: audio/wav\r\n\r\n")
        parts.append(content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    print("=" * 60)
    print("国语水平测试系统 - 接口冒烟测试")
    print("=" * 60)

    # ---------- 1. 健康检查 ----------
    print("\n[1] 健康检查 / Hello 接口")
    opener = client()
    health = call(opener, "GET", "/api/health")
    check("GET /api/health 返回 code=0", health.get("code") == 0, health)
    if health.get("code") == 0:
        data = health["data"]
        check("数据库连接正常", data.get("database") == "UP", data)
        print(f"       服务：{data.get('app')} | 评分模式：{data.get('scoring_mode')}")
        print(f"       数据：{data.get('counts')}")

    # ---------- 2. 未登录拦截 ----------
    print("\n[2] 未登录访问受保护接口")
    anon = call(client(), "GET", "/api/student/dashboard")
    check("返回 401", anon.get("code") == 401, anon)

    # ---------- 3. 管理员登录 ----------
    print("\n[3] 管理员登录 + 管理端接口")
    admin = client()
    # 先测错误密码：登录成功会清空该账号的失败计数，所以把"错误密码"放在
    # "登录成功"之前，反复跑冒烟测试不会把 admin 账号攒到锁定阈值。
    bad = call(client(), "POST", "/api/auth/login", {"username": "admin", "password": "wrong"})
    check("错误密码被拒绝", bad.get("code") == 400, bad)

    login = call(admin, "POST", "/api/auth/login", {"username": "admin", "password": "admin123"})
    check("admin 登录成功", login.get("code") == 0, login)
    check("角色为 ADMIN", (login.get("data") or {}).get("role") == "ADMIN", login)

    stats = call(admin, "GET", "/api/admin/stats")
    check("GET /api/admin/stats", stats.get("code") == 0, stats)
    if stats.get("code") == 0:
        d = stats["data"]
        print(f"       学生 {d['student_count']} 人 | 题库 {d['question_count']} 题 | 今日 {d['today_exam_count']} 场 | 平均分 {d['avg_score']}")
        check("题型平均分有 4 项", len(d.get("type_averages") or []) == 4, d.get("type_averages"))

    students = call(admin, "GET", "/api/admin/students")
    check("GET /api/admin/students", students.get("code") == 0, students)
    if students.get("code") == 0:
        check("学生列表非空", len(students["data"]) > 0, students["data"])
        print(f"       学生数：{len(students['data'])}")

    records = call(admin, "GET", "/api/admin/exam-records?page=1&size=5")
    check("GET /api/admin/exam-records 分页", records.get("code") == 0, records)
    if records.get("code") == 0:
        r = records["data"]
        check("分页字段齐全", all(k in r for k in ("list", "total", "page", "size", "total_pages")), r)
        print(f"       共 {r['total']} 条，第 {r['page']}/{r['total_pages']} 页")

    # 题库 CRUD（先清掉上次测试可能残留的题目）
    leftovers = call(admin, "GET", "/api/admin/questions?keyword=冒烟测试题&size=100")
    for row in (leftovers.get("data") or {}).get("list", []):
        call(admin, "DELETE", f"/api/admin/questions/{row['id']}")

    q_page = call(admin, "GET", "/api/admin/questions?page=1&size=3")
    check("GET /api/admin/questions", q_page.get("code") == 0, q_page)

    created = call(admin, "POST", "/api/admin/questions",
                   {"type": 1, "content": "冒烟测试题", "answer": "mào yān", "difficulty": "简单"})
    check("新增题目", created.get("code") == 0, created)
    new_id = (created.get("data") or {}).get("id")

    if new_id:
        updated = call(admin, "PUT", f"/api/admin/questions/{new_id}",
                       {"type": 2, "content": "冒烟测试题(改)", "answer": "gǎi", "difficulty": "中等"})
        check("编辑题目", updated.get("code") == 0 and updated["data"]["difficulty"] == "中等", updated)

        found = call(admin, "GET", "/api/admin/questions?keyword=冒烟测试题")
        check("关键字搜索命中", found.get("code") == 0 and found["data"]["total"] >= 1, found)

        deleted = call(admin, "DELETE", f"/api/admin/questions/{new_id}")
        check("删除题目", deleted.get("code") == 0, deleted)

    filtered = call(admin, "GET", "/api/admin/questions?type=3&page=1&size=5")
    check("按题型筛选", filtered.get("code") == 0, filtered)
    if filtered.get("code") == 0:
        check("筛选结果题型一致",
              all(q["type"] == 3 for q in filtered["data"]["list"]), filtered["data"]["list"])

    # ---------- 4. 学生登录 + 考试流程 ----------
    print("\n[4] 学生登录 + 完整考试流程")
    student = client()
    slogin = call(student, "POST", "/api/auth/login", {"username": "2024001", "password": "123456"})
    check("学生登录成功", slogin.get("code") == 0, slogin)

    forbidden = call(student, "GET", "/api/admin/stats")
    check("学生访问管理端被拒(403)", forbidden.get("code") == 403, forbidden)

    dash = call(student, "GET", "/api/student/dashboard")
    check("GET /api/student/dashboard", dash.get("code") == 0, dash)
    if dash.get("code") == 0:
        d = dash["data"]
        print(f"       考试 {d['exam_count']} 次 | 平均 {d['avg_score']} | 最高 {d['max_score']} | 当前 {d['current_level']}")

    paper = call(student, "POST", "/api/exam/start")
    check("POST /api/exam/start 随机组卷", paper.get("code") == 0, paper)
    if paper.get("code") != 0:
        return 1

    pdata = paper["data"]
    record_id = pdata["record_id"]
    check("试卷有 4 个题型", len(pdata["sections"]) == 4, pdata["sections"])
    for section in pdata["sections"]:
        items = section.get("items") or []
        check(f"题{section['type']} {section['name']} 有题目（{len(items)}）", len(items) > 0, section)

    # 提交四道题
    fake_audio = b"RIFF" + b"\x00" * 64
    for section in pdata["sections"]:
        type_no = section["type"]
        body, ctype = multipart(
            {"recordId": str(record_id), "type": str(type_no)},
            {"file": (f"rec_{type_no}.wav", fake_audio)},
        )
        result = call(student, "POST", "/api/exam/submit", raw=body, content_type=ctype)
        message = result.get("message") or ""
        if result.get("code") == 0:
            check(f"提交题{type_no} 并评分", True)
            r = result["data"]
            print(f"       题{type_no}: {r['score']}/{r['total']}  声韵调 {r['detail']}")
        elif result.get("code") == 400 and "录音" in message:
            # SCORING_MODE=ise 时假音频过不了讯飞（判为没有有效录音），属预期；
            # 真实录音的评分走 scripts/ise_e2e_test.py 验证。
            print(f"  [跳过] 题{type_no}：假音频未被采纳（{message}）")
        else:
            check(f"提交题{type_no} 并评分", False, result)

    finished = call(student, "POST", f"/api/exam/{record_id}/finish")
    check("POST /api/exam/{id}/finish 交卷", finished.get("code") == 0, finished)
    if finished.get("code") == 0:
        print(f"       总分 {finished['data']['total_score']} -> {finished['data']['level']}")

    report = call(student, "GET", f"/api/exam/records/{record_id}")
    check("GET /api/exam/records/{id} 成绩报告", report.get("code") == 0, report)
    if report.get("code") == 0:
        r = report["data"]
        check("报告含 4 个板块", len(r["sections"]) == 4, r)
        check("状态为已完成", r["status"] == "FINISHED", r)

    history = call(student, "GET", "/api/exam/records")
    check("GET /api/exam/records 历史成绩", history.get("code") == 0, history)
    if history.get("code") == 0:
        print(f"       历史记录 {len(history['data'])} 条")

    chart = call(student, "GET", "/api/exam/chart")
    check("GET /api/exam/chart 曲线数据", chart.get("code") == 0, chart)
    if chart.get("code") == 0:
        check("曲线日期与分数等长",
              len(chart["data"]["dates"]) == len(chart["data"]["scores"]), chart["data"])

    # ---------- 5. 注册 + 退出 ----------
    print("\n[5] 学生注册 + 退出登录")
    new_no = "9" + uuid.uuid4().hex[:6]
    reg = call(client(), "POST", "/api/auth/register",
               {"name": "测试同学", "student_no": new_no, "class_name": "测试班", "password": "abc123"})
    check("注册成功", reg.get("code") == 0, reg)

    dup = call(client(), "POST", "/api/auth/register",
               {"name": "测试同学", "student_no": new_no, "class_name": "测试班", "password": "abc123"})
    check("重复学号被拒绝", dup.get("code") == 400, dup)

    out = call(student, "POST", "/api/auth/logout")
    check("退出登录", out.get("code") == 0, out)
    after = call(student, "GET", "/api/student/dashboard")
    check("退出后会话失效(401)", after.get("code") == 401, after)

    print("\n" + "=" * 60)
    print(f"通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 60)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())