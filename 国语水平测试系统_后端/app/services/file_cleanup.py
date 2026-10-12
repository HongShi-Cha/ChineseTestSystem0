"""录音文件清理：按保留天数删除过期录音。

第 9 步加固：原来录音只落盘、从不删除，长期运行会把磁盘撑满。
默认保留 UPLOAD_RETENTION_DAYS 天（0 表示永久保留），服务启动时自动清一次，
管理端也可以调用接口手动触发。
"""
import logging
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

#: 只清理本系统自己写出来的录音，避免误删同目录下的其它文件
UPLOAD_FILE_PREFIX = "rec_"


def cleanup_expired_uploads(
    upload_dir: str | Path | None = None, retention_days: int | None = None
) -> dict:
    """删除超过保留期的录音文件。

    返回 {deleted, kept, freed_bytes, upload_dir, retention_days}，方便接口直接回显。
    """
    days = settings.upload_retention_days if retention_days is None else retention_days
    directory = Path(upload_dir) if upload_dir is not None else settings.upload_path

    result = {
        "deleted": 0,
        "kept": 0,
        "freed_bytes": 0,
        "upload_dir": str(directory),
        "retention_days": days,
    }

    # 0 表示永久保留：直接跳过，绝不能在"没配保留期"的情况下删数据
    if days <= 0:
        logger.debug("UPLOAD_RETENTION_DAYS=%s，跳过录音清理", days)
        return result

    if not directory.is_dir():
        logger.debug("录音目录不存在，跳过清理：%s", directory)
        return result

    cutoff = time.time() - days * 86400
    for item in directory.iterdir():
        if not item.is_file() or not item.name.startswith(UPLOAD_FILE_PREFIX):
            continue
        try:
            stat = item.stat()
        except OSError as exc:  # noqa: BLE001 - 个别文件读不到不影响整体清理
            logger.warning("读取录音文件信息失败：%s（%s）", item, exc)
            continue

        if stat.st_mtime >= cutoff:
            result["kept"] += 1
            continue

        try:
            item.unlink()
        except OSError as exc:  # noqa: BLE001 - 正在被占用等，下次启动再删
            logger.warning("删除过期录音失败：%s（%s）", item, exc)
            continue

        result["deleted"] += 1
        result["freed_bytes"] += stat.st_size

    if result["deleted"]:
        logger.info(
            "录音清理完成：删除 %s 个过期文件，释放 %.2f MB",
            result["deleted"],
            result["freed_bytes"] / 1024 / 1024,
        )
    return result