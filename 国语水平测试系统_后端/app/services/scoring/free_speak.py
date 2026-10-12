"""命题说话（自由说）评分 —— 第四题专用。

为什么不用讯飞：ISE 的中文题型只有 单字 / 词语 / 句子 / 篇章 四种，
"自由说" 这类题型需要另外购买讯飞的试卷定制服务，当前 key 用不了
（实测 category=read_recitation 会直接回 48195）。

所以第四题在本地做**流利度分析**：把录音切成 20ms 小帧算能量做 VAD，
再按 有效说话时长 / 停顿密度 / 有效发音占比 三个维度折算成百分制。
维度权重参考普通话测试"命题说话"的评分思路（说完没说完、卡不卡、连贯不连贯）。
"""
from __future__ import annotations

import logging
import math

from app.core.constants import TYPE_TOTALS
from app.core.errors import BizException
from app.services.scoring.audio import read_pcm, to_samples
from app.services.scoring.base import ScoreRequest, ScoreResult

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SIZE = SAMPLE_RATE * FRAME_MS // 1000      # 320 个采样点
TARGET_VOICED_SECONDS = 150.0                    # 说满 150 秒拿满分（限时 3 分钟）
PAUSE_MIN_MS = 400                               # 超过 400ms 才算"停顿"

#: 三维度权重：时长 45% / 流利 35% / 连贯 20%
WEIGHTS = {"duration": 0.45, "fluency": 0.35, "coherence": 0.20}


class FreeSpeakScoringService:
    """命题说话的本地评分实现。"""

    def score(self, request: ScoreRequest) -> ScoreResult:
        try:
            pcm = read_pcm(request.audio_path)
        except ValueError as exc:
            raise BizException(str(exc), 400) from exc
        if len(pcm) < SAMPLE_RATE:  # 不足 0.5 秒
            raise BizException("没有采集到有效录音，请重新录制本题", 400)

        samples = to_samples(pcm)
        frame_rms = _frame_rms(samples)
        if not frame_rms:
            raise BizException("没有采集到有效录音，请重新录制本题", 400)

        voiced = _voiced_flags(frame_rms)
        total_seconds = len(frame_rms) * FRAME_MS / 1000.0
        voiced_seconds = sum(1 for flag in voiced if flag) * FRAME_MS / 1000.0
        pauses = _pause_runs(voiced)
        longest_pause = max((length for length in pauses), default=0.0)
        pause_count = sum(1 for length in pauses if length * 1000 >= PAUSE_MIN_MS)

        duration_score = min(1.0, voiced_seconds / TARGET_VOICED_SECONDS) * 100.0
        pause_per_minute = pause_count / max(voiced_seconds / 60.0, 0.5)
        fluency_score = _clamp(100 - max(0.0, pause_per_minute - 6) * 6 - max(0.0, longest_pause - 2) * 8, 40, 100)
        ratio = voiced_seconds / total_seconds if total_seconds else 0.0
        coherence_score = _clamp(60 + (ratio - 0.5) * 130, 40, 100)

        percent = (
            duration_score * WEIGHTS["duration"]
            + fluency_score * WEIGHTS["fluency"]
            + coherence_score * WEIGHTS["coherence"]
        )
        total = TYPE_TOTALS.get(request.type, 100.0)
        score = round(total * percent / 100.0, 1)

        logger.info(
            "【命题说话·本地评分】记录%s 有效说话 %.1fs / 停顿 %d 次 / 占比 %.0f%% -> %.1f",
            request.record_id, voiced_seconds, pause_count, ratio * 100, score,
        )
        return ScoreResult(
            type=request.type,
            score=score,
            total=total,
            detail={
                "engine": "local_free_speak",
                "shengmu": None,          # 自由说没有声韵调拆分，前端显示 "-"
                "yunmu": None,
                "shengdiao": None,
                "liulidu": int(round(fluency_score)),
                "changdu": int(round(duration_score)),
                "lian_guan": int(round(coherence_score)),
                "voiced_seconds": round(voiced_seconds, 1),
                "total_seconds": round(total_seconds, 1),
                "pause_count": pause_count,
                "longest_pause": round(longest_pause, 1),
            },
        )


def _frame_rms(samples) -> list[float]:
    """按 20ms 分帧算 RMS（0~32768）。"""
    frames = []
    for start in range(0, len(samples) - FRAME_SIZE + 1, FRAME_SIZE):
        chunk = samples[start:start + FRAME_SIZE]
        total = 0
        for value in chunk:
            total += value * value
        frames.append(math.sqrt(total / FRAME_SIZE))
    return frames


def _voiced_flags(frame_rms: list[float]) -> list[bool]:
    """自适应门限：取 10% 分位当噪声底，底噪的 3 倍（且不低于 250）作为说话门限。"""
    ordered = sorted(frame_rms)
    noise = ordered[int(len(ordered) * 0.1)] if ordered else 0.0
    threshold = max(noise * 3.0, 250.0)
    return [value >= threshold for value in frame_rms]


def _pause_runs(voiced: list[bool]) -> list[float]:
    """返回每段静音的时长（秒）。"""
    runs, current = [], 0
    for flag in voiced:
        if flag:
            if current:
                runs.append(current * FRAME_MS / 1000.0)
                current = 0
        else:
            current += 1
    if current:
        runs.append(current * FRAME_MS / 1000.0)
    return runs


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))