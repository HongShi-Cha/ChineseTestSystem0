r"""讯飞 ISE 连通性诊断：区分“本地网络/代理问题”与“讯飞侧限流”。

用法：
    .venv\Scripts\python.exe scripts\ise_diag.py
"""
from __future__ import annotations

import os
import socket
import ssl
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

HOST = "ise-api.xfyun.cn"
PORT = 443


def one_round(index: int) -> None:
    started = time.time()
    try:
        raw = socket.create_connection((HOST, PORT), timeout=15)
    except OSError as exc:
        print("  [%d] TCP 连接失败：%r" % (index, exc))
        return
    print("  [%d] TCP 已连接 peer=%s（%.2fs）" % (index, raw.getpeername()[0], time.time() - started))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        tls = ctx.wrap_socket(raw, server_hostname=HOST)
        print("  [%d] TLS 握手成功，协议=%s（%.2fs）" % (index, tls.version(), time.time() - started))
        tls.close()
    except Exception as exc:  # noqa: BLE001
        print("  [%d] TLS 握手失败：%r" % (index, exc))
        try:
            raw.close()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    print("[diag] 代理环境变量：", {k: v for k, v in os.environ.items() if "proxy" in k.lower()})
    for index in range(1, 6):
        one_round(index)
        time.sleep(1.0)


if __name__ == "__main__":
    main()