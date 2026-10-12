"""轻量限流工具（进程内，第 10 步引入）。

两样东西：

* ``SlidingWindowLimiter`` —— 按 key 的滑动窗口计数，用来挡注册刷号这类低频滥用；
* ``ConcurrencyGate``      —— 并发闸门，把讯飞评测压在官方并发上限之内。

两者都是**进程内**状态：单 worker 部署时就是全局的；多 worker 时每个 worker 各算各的。
所以公网部署的第一道防线应该放在 nginx（见 deploy/nginx.conf 里的 limit_req），
这里只是"系统别把自己打挂"的兜底。
"""
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings
from app.core.constants import CODE_TOO_MANY_REQUESTS
from app.core.errors import BizException

logger = logging.getLogger(__name__)

#: key 数量超过这个值就顺手清一遍过期的，避免长期运行内存只涨不降
_SWEEP_THRESHOLD = 4096


class SlidingWindowLimiter:
    """按 key 的滑动窗口计数器：窗口内超过 limit 次就拒绝。"""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = max(1, int(limit))
        self.window = max(1, int(window_seconds))
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """记一次访问；返回 False 表示这次超限、应该被拒绝。"""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            self._sweep(now, cutoff)
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        """清空计数（测试用）。"""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    # 调用方必须已持有 self._lock
    def _sweep(self, now: float, cutoff: float) -> None:
        if len(self._hits) < _SWEEP_THRESHOLD:
            return
        for key, hits in list(self._hits.items()):
            while hits and hits[0] < cutoff:
                hits.popleft()
            if not hits:
                self._hits.pop(key, None)


class ConcurrencyGate:
    """并发闸门：同时最多放行 limit 个，排队超过 timeout 秒就放弃。"""

    def __init__(self, limit: int, timeout_seconds: float) -> None:
        self.limit = max(1, int(limit))
        self.timeout = max(0.0, float(timeout_seconds))
        self._sem = threading.BoundedSemaphore(self.limit)

    @contextmanager
    def slot(self, busy_message: str = "当前请求过于集中，请稍后重试") -> Iterator[None]:
        """拿到一个并发名额才继续；等不到就抛业务错误（429）。"""
        if not self._sem.acquire(timeout=self.timeout):
            logger.warning(
                "并发闸门已满（limit=%s），排队超过 %s 秒，本次拒绝", self.limit, self.timeout
            )
            raise BizException(busy_message, CODE_TOO_MANY_REQUESTS)
        try:
            yield
        finally:
            self._sem.release()


#: 注册限流：同一 IP 每小时最多注册 REGISTER_MAX_PER_HOUR 个
register_limiter = SlidingWindowLimiter(settings.register_max_per_hour, 3600)

#: 讯飞评测并发闸门：并发上限 + 排队等待上限
scoring_gate = ConcurrencyGate(settings.ise_max_concurrency, settings.ise_max_wait_seconds)