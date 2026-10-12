"""录音读取工具：不管前端传的是裸 PCM 还是 WAV，统一取出 16k/16bit/单声道 PCM。

背景：浏览器 MediaRecorder 录出来的是 webm/opus，前端 js/main.js 会先用
AudioContext 解码 + 重采样成 16k 单声道，再以 **裸 PCM** 上传（后缀 .pcm）；
但手工用别的工具测试时可能传的是 WAV，所以这里两种都兼容。
"""
from __future__ import annotations

import array
import struct
import sys
from pathlib import Path

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # 16bit 单声道


def read_pcm(path: str) -> bytes:
    """读取录音文件，返回 16k/16bit/单声道裸 PCM 字节。"""
    if not path:
        return b""
    blob = Path(path).read_bytes()
    if blob[:4] != b"RIFF":
        return blob

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

    if fmt and len(fmt) >= 16:
        channels = struct.unpack("<H", fmt[2:4])[0]
        rate = struct.unpack("<I", fmt[4:8])[0]
        bits = struct.unpack("<H", fmt[14:16])[0]
        if (rate, bits, channels) != (SAMPLE_RATE, 16, 1):
            raise ValueError(
                "音频格式不符合讯飞要求：需要 16000Hz / 16bit / 单声道，"
                f"当前是 {rate}Hz / {bits}bit / {channels}声道"
            )
    return data


def to_samples(pcm: bytes) -> array.array:
    """PCM 字节 -> int16 采样点数组（小端）。"""
    usable = len(pcm) - (len(pcm) % 2)
    samples = array.array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def duration_seconds(pcm: bytes) -> float:
    return len(pcm) / float(BYTES_PER_SECOND)