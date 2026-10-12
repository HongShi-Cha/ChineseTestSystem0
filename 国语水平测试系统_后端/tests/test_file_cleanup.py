"""录音清理策略的单元测试：只删过期录音，0 表示永久保留。"""
import os
import time

from app.core.config import settings
from app.services.file_cleanup import UPLOAD_FILE_PREFIX, cleanup_expired_uploads


def write_recording(directory, name: str, age_days: float, size: int = 16):
    """造一个"看起来是 N 天前录的"文件。"""
    path = directory / name
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_deletes_only_expired_recordings(tmp_path):
    old = write_recording(tmp_path, UPLOAD_FILE_PREFIX + "1_1_a.pcm", age_days=30)
    fresh = write_recording(tmp_path, UPLOAD_FILE_PREFIX + "2_1_b.pcm", age_days=1)
    foreign = write_recording(tmp_path, "keep-me.txt", age_days=30)

    result = cleanup_expired_uploads(tmp_path, retention_days=14)

    assert result["deleted"] == 1
    assert result["kept"] == 1
    assert result["freed_bytes"] == 16
    assert not old.exists()
    assert fresh.exists()
    assert foreign.exists()          # 不是本系统写出来的文件，绝不碰


def test_zero_retention_keeps_everything(tmp_path):
    """UPLOAD_RETENTION_DAYS=0 = 永久保留：一个都不能删。"""
    old = write_recording(tmp_path, UPLOAD_FILE_PREFIX + "1_1_a.pcm", age_days=999)

    result = cleanup_expired_uploads(tmp_path, retention_days=0)

    assert result["deleted"] == 0
    assert result["kept"] == 0
    assert old.exists()


def test_missing_directory_is_tolerated(tmp_path):
    result = cleanup_expired_uploads(tmp_path / "nope", retention_days=14)
    assert result["deleted"] == 0
    assert result["freed_bytes"] == 0


def test_retention_defaults_to_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_retention_days", 1)
    write_recording(tmp_path, UPLOAD_FILE_PREFIX + "1_1_a.pcm", age_days=3)
    assert cleanup_expired_uploads(tmp_path)["deleted"] == 1


def test_subdirectories_are_ignored(tmp_path):
    nested = tmp_path / (UPLOAD_FILE_PREFIX + "nested")
    nested.mkdir()
    result = cleanup_expired_uploads(tmp_path, retention_days=1)
    assert result["deleted"] == 0
    assert nested.exists()