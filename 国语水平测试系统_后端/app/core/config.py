"""应用配置：从 .env 读取环境变量（pydantic-settings）。

Mock data added, backend calls removed for Python demo.
（本文件对应"第 1 步：骨架"的配置层）
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import EXAM_DURATION_SECONDS

# 后端根目录：.../国语水平测试系统_后端
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """全部配置项，字段名小写下划线，与 .env 中的变量一一对应。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "国语水平测试系统"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    debug: bool = True

    # ---------- MySQL ----------
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "guoyu_test"

    # ---------- 会话 ----------
    session_secret_key: str = "dev-secret-change-me"
    session_max_age: int = 86400

    # ---------- 目录 ----------
    frontend_dir: str = ""
    upload_dir: str = ""

    # ---------- 演示数据 ----------
    # 首次启动时是否生成演示用的考试成绩（表非空则跳过）
    seed_demo_data: bool = True

    # ---------- 考试闭环保护（第 9 步） ----------
    # 整场考试时长（秒）：组卷接口返回给前端的 duration_seconds 也取这里，保证前后端口径一致
    exam_duration_seconds: int = EXAM_DURATION_SECONDS
    # 交卷宽限期（秒）：倒计时结束后再多给这么多秒，容忍提交在途的请求
    exam_deadline_grace_seconds: int = 30
    # 单个学生允许完成的考试场次上限；0 = 不限次数
    max_exam_attempts: int = 0
    # 录音保留天数；0 = 永久保留。超期录音由启动时/管理端清理任务删除
    upload_retention_days: int = 14
    # 单次录音上传大小上限（字节）：命题说话 3 分钟 16k/16bit 单声道约 5.8MB，20MB 留足余量
    max_upload_bytes: int = 20 * 1024 * 1024

    # ---------- 公网部署与安全加固（第 10 步） ----------
    # 是否开放 /api/docs 在线接口文档；公网部署建议改成 false
    enable_docs: bool = True
    # 允许跨域的来源，逗号分隔；留空 = 只放行本机调试地址（同源部署其实用不到 CORS）
    cors_origins: str = ""
    # 会话 Cookie 是否只走 HTTPS：用 nginx + 证书部署后必须改成 true
    session_cookie_secure: bool = False
    # 是否追加安全响应头（nosniff / 防 iframe 嵌套 / Referrer-Policy…）
    security_headers: bool = True
    # 登录失败锁定：同一账号 / 同一 IP 在窗口内失败多少次就锁。
    # 账号级阈值要小（防针对某个账号的撞库）；IP 级阈值要大得多，因为
    # 校园网常常整栋楼共用一个出口 IP，阈值太小会把整个学校误伤掉。
    login_max_failures: int = 5
    login_max_ip_failures: int = 100
    # 登录失败统计窗口，同时也是锁定时长（秒），默认 15 分钟
    login_window_seconds: int = 900
    # 注册接口限流：同一 IP 每小时最多注册几个（防刷号）
    register_max_per_hour: int = 5
    # 讯飞评测最大并发（官方默认 50 路，留出余量）与排队等待上限（秒）
    ise_max_concurrency: int = 30
    ise_max_wait_seconds: int = 20

    @property
    def exam_deadline_seconds(self) -> int:
        """本场考试的硬截止时间（秒）= 时长 + 宽限。"""
        return max(0, self.exam_duration_seconds) + max(0, self.exam_deadline_grace_seconds)

    @property
    def max_upload_mb(self) -> int:
        """上传上限的 MB 展示值（用于错误提示）。"""
        return max(1, self.max_upload_bytes // (1024 * 1024))

    # ---------- 评分 ----------
    scoring_mode: str = "mock"
    ise_app_id: str = ""
    ise_api_key: str = ""
    ise_api_secret: str = ""
    ise_host: str = "ise-api.xfyun.cn"
    ise_send_interval: float = 0.01   # 音频帧间隔（秒），官方建议 0.04，实测 0.01 结果一致且更快
    ise_timeout: int = 60             # 单次评测读取超时（秒）
    ise_max_retry: int = 2            # 网络抖动时的重试次数
    ise_fallback_mock: bool = True    # 讯飞不可用时是否回退模拟评分（正式部署建议改 False）

    @property
    def database_url(self) -> str:
        """SQLAlchemy 连接串（PyMySQL 驱动）。"""
        return (
            "mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4".format(
                user=self.db_user,
                pwd=self.db_password,
                host=self.db_host,
                port=self.db_port,
                name=self.db_name,
            )
        )

    @property
    def frontend_path(self) -> Path:
        """前端静态目录，默认取后端目录的上一级。"""
        raw = self.frontend_dir.strip() or str(BACKEND_DIR.parent)
        return Path(raw)

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS 白名单：显式配置优先，否则只放行本机调试地址。"""
        raw = (self.cors_origins or "").strip()
        if not raw:
            hosts = ("127.0.0.1", "localhost")
            return [f"http://{host}:{port}" for port in (self.app_port, 5500) for host in hosts]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def upload_path(self) -> Path:
        """录音上传目录，默认 data/uploads。"""
        raw = self.upload_dir.strip() or str(BACKEND_DIR / "data" / "uploads")
        return Path(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()