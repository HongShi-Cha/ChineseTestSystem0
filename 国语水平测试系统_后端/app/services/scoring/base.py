"""评分服务的抽象接口与数据结构。"""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ScoreRequest:
    """一次评分请求：录音 + 参考文本。"""

    record_id: int
    type: int
    text: str
    audio_path: str = ""
    audio_name: str = ""


@dataclass
class ScoreResult:
    """评分结果：得分 / 满分 / 声韵调详情。"""

    type: int
    score: float
    total: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "score": self.score,
            "total": self.total,
            "detail": self.detail,
        }


class ScoringService(Protocol):
    """面向接口编程：换评分引擎不用改业务代码。"""

    def score(self, request: ScoreRequest) -> ScoreResult:
        ...