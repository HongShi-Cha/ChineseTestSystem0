r"""讯飞 ISE 联调探针 —— 按官方 v2 协议发帧，并把原始评测 XML 落盘。

官方协议（https://www.xfyun.cn/doc/Ise/IseAPI.html）：
    1) 参数上传阶段：data.status=0，business.cmd="ssb"，此时不带音频；
    2) 第一帧音频：business.cmd="auw"、aus=1、data.status=1；
    3) 中间帧音频：business.cmd="auw"、aus=2、data.status=1；
    4) 最后一帧音频：business.cmd="auw"、aus=4、data.status=2。

用法：
    .venv\Scripts\python.exe scripts\ise_probe.py --audio data\samples\word.wav --category read_word --text 热爱
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import math
import os
import select
import ssl
import struct
import sys
import time
import traceback
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.config import settings  # noqa: E402

try:
    import websocket  # noqa: E402
except ImportError:  # pragma: no cover
    raise SystemExit("缺少依赖，请先执行：pip install websocket-client")

HOST = (settings.ise_host or "ise-api.xfyun.cn").strip()
PATH = "/v2/open-ise"
FRAME_SIZE = 1280
SEND_INTERVAL = 0.04
POLL_EVERY = 10
OUT_DIR = os.path.join(BASE_DIR, "data", "ise_probe")


def signed_url() -> str:
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    origin = "host: %s\ndate: %s\nGET %s HTTP/1.1" % (HOST, date, PATH)
    signature = hmac.new(settings.ise_api_secret.encode("utf-8"), origin.encode("utf-8"), hashlib.sha256).digest()
    auth_origin = (
        'api_key="%s", algorithm="hmac-sha256", headers="host date request-line", signature="%s"'
        % (settings.ise_api_key, base64.b64encode(signature).decode())
    )
    return "wss://%s%s?%s" % (HOST, PATH, urlencode({
        "authorization": base64.b64encode(auth_origin.encode("utf-8")).decode(),
        "date": date,
        "host": HOST,
    }))


def ssb_frame(category: str, text: str) -> dict:
    business = {
        "sub": "ise",
        "ent": "cn_vip",
        "category": category,
        "cmd": "ssb",
        "text": "\ufeff" + text,
        "tte": "utf-8",
        "ttp_skip": True,
        "auf": "audio/L16;rate=16000",
        "aue": "raw",
        "rstcd": "utf8",
        "rst": "entirety",
        "ise_unite": "1",
        "extra_ability": "multi_dimension;syll_phone_err_msg",
        "group": "adult",
        "check_type": "common",
    }
    return {"common": {"app_id": settings.ise_app_id}, "business": business, "data": {"status": 0}}


def auw_frame(chunk: bytes, aus: int, status: int) -> dict:
    return {
        "business": {"cmd": "auw", "aus": aus},
        "data": {"status": status, "data": base64.b64encode(chunk).decode()},
    }


def drain(ws, parts, messages, tag: str) -> bool:
    """读干净当前已到达的消息；返回 False 代表服务端报错。"""
    while True:
        try:
            readable = select.select([ws.sock], [], [], 0)[0]
        except Exception:  # noqa: BLE001
            readable = [True]
        pending = 0
        try:
            pending = ws.sock.pending()
        except Exception:  # noqa: BLE001
            pending = 0
        if not readable and not pending:
            return True
        try:
            message = json.loads(ws.recv())
        except Exception as exc:  # noqa: BLE001
            messages.append("%s 读取出错：%r" % (tag, exc))
            print("  !! %s" % messages[-1])
            return False
        code = message.get("code")
        payload = message.get("data") or {}
        messages.append("%s code=%s message=%s status=%s" % (tag, code, message.get("message"), payload.get("status")))
        print("  <- %s" % messages[-1])
        if code != 0:
            return False
        if payload.get("data"):
            parts.append(base64.b64decode(payload["data"]).decode("utf-8"))
        if payload.get("status") == 2:
            return False


def run_once(category: str, text: str, audio: bytes, interval: float = SEND_INTERVAL) -> tuple:
    messages = []
    parts = []
    ws = websocket.create_connection(signed_url(), timeout=30, sslopt={"cert_reqs": ssl.CERT_NONE})
    try:
        ws.send(json.dumps(ssb_frame(category, text)))
        ws.settimeout(1.5)
        try:
            early = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            early = None
        finally:
            ws.settimeout(60)
        if early is not None:
            messages.append("ssb code=%s message=%s" % (early.get("code"), early.get("message")))
            print("  <- %s" % messages[-1])
            if early.get("code") != 0:
                return False, "", messages

        chunks = [audio[i:i + FRAME_SIZE] for i in range(0, len(audio), FRAME_SIZE)]
        started = time.time()
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            aus = 4 if last else (1 if index == 0 else 2)
            try:
                ws.send(json.dumps(auw_frame(chunk, aus, 2 if last else 1)))
            except Exception as exc:  # noqa: BLE001
                messages.append("发送第 %d/%d 帧失败（用时 %.1fs）：%r" % (index, len(chunks), time.time() - started, exc))
                print("  !! %s" % messages[-1])
                drain(ws, parts, messages, "断开前")
                return False, "", messages
            if not last:
                time.sleep(interval)
            if index % POLL_EVERY == 0:
                if not drain(ws, parts, messages, "第%d帧" % index):
                    return False, "".join(parts), messages
        print("  .. 音频发完：%d 帧 / %d 字节 / 用时 %.1fs" % (len(chunks), len(audio), time.time() - started))

        quiet = 0
        while True:
            try:
                message = json.loads(ws.recv())
            except Exception as exc:  # noqa: BLE001
                messages.append("接收中断：%r" % (exc,))
                print("  !! %s" % messages[-1])
                return False, "".join(parts), messages
            code = message.get("code")
            payload = message.get("data") or {}
            if code != 0 or payload.get("status") == 2:
                messages.append("code=%s message=%s status=%s" % (code, message.get("message"), payload.get("status")))
                print("  <- %s" % messages[-1])
            else:
                quiet += 1
            if code != 0:
                return False, "", messages
            if payload.get("data"):
                parts.append(base64.b64decode(payload["data"]).decode("utf-8"))
            if payload.get("status") == 2:
                break
        if quiet:
            print("  .. 中间成功帧 %d 个（略）" % quiet)
        xml = "".join(parts)
        return (bool(xml), xml, messages)
    finally:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass


def pcm_tone(seconds: float = 3.0, rate: int = 16000, freq: float = 220.0) -> bytes:
    out = bytearray()
    for i in range(int(seconds * rate)):
        env = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / rate)
        value = int(12000 * env * math.sin(2 * math.pi * freq * i / rate))
        out += struct.pack("<h", max(-32768, min(32767, value)))
    return bytes(out)


def load_audio(path: str, seconds: float = 0.0) -> bytes:
    if not path:
        print("[audio] 未指定音频，使用 3 秒纯音探协议（内容无意义）")
        return pcm_tone()
    with open(path, "rb") as fp:
        blob = fp.read()
    if blob[:4] != b"RIFF":
        print("[audio] 按裸 PCM 处理：%s（%d 字节）" % (path, len(blob)))
        data = blob
    else:
        pos, fmt, data = 12, None, b""
        while pos + 8 <= len(blob):
            chunk_id = blob[pos:pos + 4]
            size = struct.unpack("<I", blob[pos + 4:pos + 8])[0]
            body = blob[pos + 8:pos + 8 + size]
            if chunk_id == b"fmt ":
                fmt = body
            elif chunk_id == b"data":
                data = body
            pos += 8 + size + (size & 1)
        if fmt:
            channels = struct.unpack("<H", fmt[2:4])[0]
            rate = struct.unpack("<I", fmt[4:8])[0]
            bits = struct.unpack("<H", fmt[14:16])[0]
            print("[audio] WAV 采样率=%s 位深=%s 声道=%s，PCM %d 字节（%.2f 秒）" % (
                rate, bits, channels, len(data), len(data) / 32000.0))
            if (rate, bits, channels) != (16000, 16, 1):
                print("[audio] 警告：讯飞要求 16000/16bit/单声道，该文件不符合")
    if seconds > 0:
        cut = int(seconds * 32000)
        if len(data) > cut:
            print("[audio] 按要求截断到前 %.2f 秒" % seconds)
            data = data[:cut]
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="read_syllable")
    parser.add_argument("--text", default="白买家听你")
    parser.add_argument("--audio", default="", help="16k/16bit/单声道 WAV 或裸 PCM")
    parser.add_argument("--seconds", type=float, default=0.0, help="只取音频前 N 秒")
    parser.add_argument("--interval", type=float, default=SEND_INTERVAL, help="音频帧发送间隔（秒）")
    parser.add_argument("--out", default="result", help="输出 XML 文件名（不含扩展名）")
    args = parser.parse_args()

    audio = load_audio(args.audio, args.seconds)
    print("[probe] category=%s text=%r 音频=%d 字节 interval=%.3fs" % (
        args.category, args.text, len(audio), args.interval))
    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        ok, xml, messages = run_once(args.category, args.text, audio, args.interval)
    except Exception:  # noqa: BLE001
        print("[probe] 异常：")
        print(traceback.format_exc())
        return
    if ok:
        out = os.path.join(OUT_DIR, "%s.xml" % args.out)
        with open(out, "w", encoding="utf-8") as fp:
            fp.write(xml)
        print("[probe] [OK] 原始 XML：%s（%d 字符）" % (out, len(xml)))
    else:
        print("[probe] [FAIL] 消息：%s" % " | ".join(messages[-3:]))


if __name__ == "__main__":
    main()