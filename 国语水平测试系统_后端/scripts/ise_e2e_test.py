"""讯飞评测端到端联调：登录 -> 组卷 -> 上传录音 -> 评分 -> 交卷 -> 报表。

用法（在 国语水平测试系统_后端 目录下，需先启动服务）：
    # 1) 先拿一份试卷（记下 record_id，并把各题参考文本导出备用）
    .venv\\Scripts\\python.exe scripts\\ise_e2e_test.py --paper-out data\\ise_probe\\paper.json

    # 2) 按参考文本生成/录制音频后逐题上传
    .venv\\Scripts\\python.exe scripts\\ise_e2e_test.py --record 3 --audio 3=data\\samples\\q3.wav

    # 3) 交卷并打印成绩报告
    .venv\\Scripts\\python.exe scripts\\ise_e2e_test.py --record 3 --finish
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.request
import uuid

BASE = "http://127.0.0.1:8080"


def make_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(opener, path: str, data=None, method: str = "POST", headers=None):
    request = urllib.request.Request(BASE + path, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with opener.open(request, timeout=600) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("code") != 0:
        raise SystemExit(f"{path} 失败：code={body.get('code')} message={body.get('message')}")
    return body.get("data")


def post_json(opener, path: str, payload: dict):
    return call(opener, path, json.dumps(payload).encode("utf-8"), headers={
        "Content-Type": "application/json; charset=utf-8",
    })


def post_file(opener, path: str, fields: dict, file_field: str, filename: str, content: bytes):
    boundary = "----ise" + uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8")
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return call(opener, path, bytes(body), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="2024001")
    parser.add_argument("--password", default="123456")
    parser.add_argument("--paper-out", default="", help="把试卷 JSON 写到该文件")
    parser.add_argument("--record", type=int, default=0, help="已有考试记录 id（留空则新开一场）")
    parser.add_argument("--audio", action="append", default=[],
                        help="要上传的录音，格式 题型=文件路径，可重复")
    parser.add_argument("--finish", action="store_true", help="上传完交卷并打印报告")
    args = parser.parse_args()

    opener = make_opener()
    profile = post_json(opener, "/api/auth/login", {"username": args.user, "password": args.password})
    print(f"[e2e] 登录成功：{profile.get('name')}（{profile.get('student_no')}）")

    if args.record:
        record_id = args.record
    else:
        paper = post_json(opener, "/api/exam/start", {})
        record_id = paper["record_id"]
        print(f"[e2e] 试卷 record_id={record_id} 时长={paper.get('duration_seconds')}s")
        for section in paper.get("sections", []):
            text = "".join(section.get("items") or [])
            print(f"  第{section['type']}题 {section['name']}：《{text[:24]}{'…' if len(text) > 24 else ''}》"
                  f"（{len(text)} 字 / 满分 {section.get('total') or ''}）")
        if args.paper_out:
            path = args.paper_out
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(paper, fp, ensure_ascii=False, indent=2)
            print(f"[e2e] 试卷已导出：{path}")

    for item in args.audio:
        type_no, _, path = item.partition("=")
        with open(path, "rb") as fp:
            content = fp.read()
        print(f"[e2e] 上传第 {type_no} 题：{path}（{len(content)} 字节）…")
        result = post_file(opener, "/api/exam/submit",
                           {"recordId": str(record_id), "type": type_no},
                           "file", os.path.basename(path), content)
        detail = result.get("detail") or {}
        print(f"  -> 得分 {result.get('score')}/{result.get('total')}，"
              f"声母 {detail.get('shengmu')} 韵母 {detail.get('yunmu')} 声调 {detail.get('shengdiao')}，"
              f"引擎 {detail.get('engine')}")

    if args.finish:
        summary = post_json(opener, f"/api/exam/{record_id}/finish", {})
        print(f"[e2e] 交卷：总分 {summary.get('total_score')} 等级 {summary.get('level')}")
        report = call(opener, f"/api/exam/records/{record_id}", method="GET")
        print(f"[e2e] 成绩报告 record_id={report['record_id']} {report['total_score']}（{report['level']}）")
        for section in report.get("sections", []):
            detail = section.get("detail") or {}
            print(f"  第{section['type']}题 {section['title']}：{section.get('score')}/{section.get('total')}"
                  f"  声韵调 {detail.get('shengmu')}/{detail.get('yunmu')}/{detail.get('shengdiao')}"
                  f"  引擎 {detail.get('engine')}")


if __name__ == "__main__":
    main()