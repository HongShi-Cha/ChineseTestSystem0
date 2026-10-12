"""模拟评分：先让整个考试流程跑通。

加了随机波动，让每次考试分数不完全一样，更像真实系统。
"""
import logging
import random

from app.core.constants import TYPE_TOTALS
from app.services.scoring.base import ScoreRequest, ScoreResult

logger = logging.getLogger(__name__)

#: 各题型基准分（对应满分 10 / 20 / 30 / 40）
BASE_SCORE = {1: 8.6, 2: 17.2, 3: 26.3, 4: 35.4}


class MockScoringService:
    """模拟评分实现。"""

    def score(self, request: ScoreRequest) -> ScoreResult:
        type_no = request.type
        total = TYPE_TOTALS.get(type_no, 100.0)
        base = BASE_SCORE.get(type_no, total * 0.86)

        # 基准分 ±1 分的随机波动，保留 1 位小数
        score = round(base + (random.random() - 0.5) * 2, 1)
        score = max(0.0, min(total, score))

        # 声韵调详情（百分比，模拟）
        detail = {
            "shengmu": 88 + random.randint(0, 7),
            "yunmu": 85 + random.randint(0, 7),
            "shengdiao": 84 + random.randint(0, 7),
        }

        logger.info("【模拟评分】记录%s 题%s 得分 %s/%s", request.record_id, type_no, score, total)
        return ScoreResult(type=type_no, score=score, total=total, detail=detail)