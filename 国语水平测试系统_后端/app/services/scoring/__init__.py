"""评分适配层：按 .env 的 SCORING_MODE 选择实现。

mock = MockScoringService（默认，无需外网）
ise  = 讯飞语音评测：第 1~3 题走 IseScoringService，第 4 题命题说话走本地流利度评分
       （讯飞中文题型没有"自由说"，见 free_speak.py 顶部说明）
"""
from functools import lru_cache
import logging

from app.core.config import settings
from app.core.errors import BizException
from app.core.limits import scoring_gate
from app.services.scoring.base import ScoreRequest, ScoreResult, ScoringService

logger = logging.getLogger(__name__)


class HybridScoringService:
    """按题型分发 + 失败兜底。"""

    def __init__(self, ise: ScoringService, free_speak: ScoringService, mock: ScoringService) -> None:
        self.ise = ise
        self.free_speak = free_speak
        self.mock = mock

    def score(self, request: ScoreRequest) -> ScoreResult:
        # 浏览器不支持录音时会传一个空文件，这种情况用模拟分保证演示流程能走完
        if not request.audio_path:
            return self._mock_fallback(request, "没有收到录音文件")

        try:
            if request.type == 4:
                return self.free_speak.score(request)
            # 第 10 步：讯飞默认只有 50 路并发，几十个人同时交录音会把配额打满。
            # 这里用并发闸门排队，排太久就明确告诉学生稍后再试，而不是把服务拖死。
            with scoring_gate.slot("当前评测排队人数较多，请稍后重新提交本题"):
                return self.ise.score(request)
        except BizException:
            raise                      # 业务错误（录音太短、乱读…）原样抛给前端提示重录
        except Exception as exc:  # noqa: BLE001
            logger.exception("评分失败：%s", exc)
            if not settings.ise_fallback_mock:
                raise BizException(f"评分服务暂时不可用：{exc}", 500) from exc
            return self._mock_fallback(request, str(exc))

    def _mock_fallback(self, request: ScoreRequest, reason: str) -> ScoreResult:
        logger.warning("第 %s 题改用模拟评分，原因：%s", request.type, reason)
        result = self.mock.score(request)
        result.detail["engine"] = "mock_fallback"
        result.detail["fallback_reason"] = reason[:120]
        return result


@lru_cache(maxsize=1)
def get_scoring_service() -> ScoringService:
    """返回当前生效的评分实现（单例）。"""
    mode = (settings.scoring_mode or "mock").strip().lower()
    if mode == "ise":
        from app.services.scoring.free_speak import FreeSpeakScoringService
        from app.services.scoring.ise import IseScoringService
        from app.services.scoring.mock import MockScoringService

        return HybridScoringService(IseScoringService(), FreeSpeakScoringService(), MockScoringService())

    from app.services.scoring.mock import MockScoringService

    return MockScoringService()


__all__ = ["ScoreRequest", "ScoreResult", "ScoringService", "get_scoring_service"]