"""数据库连接：引擎 + 会话工厂 + FastAPI 依赖。

连接串来自 .env 中的 DB_* 配置，驱动为 PyMySQL。
"""
import logging
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,      # 取连接前先 ping 一下，避免 MySQL 8 小时断连
    pool_recycle=3600,
    pool_size=5,
    max_overflow=10,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话，用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """按模型建表（表已存在则跳过），供首次启动使用。"""
    from app import models  # noqa: F401 - 触发模型注册

    Base.metadata.create_all(bind=engine)


def ping() -> bool:
    """探活：数据库是否可连接。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - 探活失败不应该抛给调用方
        logger.warning("数据库连接失败: %s", exc)
        return False