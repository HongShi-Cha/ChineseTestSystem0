"""等级判定与题型常量的一致性测试。"""
import pytest

from app.core.config import settings
from app.core.constants import (
    EXAM_DURATION_SECONDS,
    SECTION_TITLES,
    TYPE_DURATIONS,
    TYPE_LIMIT_TEXTS,
    TYPE_NAMES,
    TYPE_PICK_COUNTS,
    TYPE_TOTALS,
)
from app.core.levels import level_of

ALL_TYPES = (1, 2, 3, 4)


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "一级甲等"),
        (97, "一级甲等"),
        (96.9, "一级乙等"),
        (92, "一级乙等"),
        (91.9, "二级甲等"),
        (87, "二级甲等"),
        (86.9, "二级乙等"),
        (80, "二级乙等"),
        (79.9, "三级甲等"),
        (70, "三级甲等"),
        (69.9, "三级乙等"),
        (60, "三级乙等"),
        (59.9, "不入级"),
        (0, "不入级"),
    ],
)
def test_level_boundaries(score, expected):
    assert level_of(score) == expected


def test_level_of_none_is_empty():
    assert level_of(None) == ""


def test_type_totals_sum_to_100():
    assert sum(TYPE_TOTALS.values()) == 100.0


def test_every_type_has_complete_metadata():
    for type_no in ALL_TYPES:
        assert TYPE_NAMES[type_no]
        assert SECTION_TITLES[type_no]
        assert TYPE_PICK_COUNTS[type_no] > 0
        assert TYPE_DURATIONS[type_no] > 0
        assert TYPE_LIMIT_TEXTS[type_no]
        assert TYPE_TOTALS[type_no] > 0


def test_section_durations_add_up_to_exam_duration():
    """四个板块的限时之和必须等于整场考试时长，否则倒计时和分题限时会互相打架。"""
    assert sum(TYPE_DURATIONS.values()) == EXAM_DURATION_SECONDS


def test_exam_duration_setting_matches_constant():
    """.env 里的 EXAM_DURATION_SECONDS 若被改动，这里会第一时间提醒。"""
    assert settings.exam_duration_seconds == EXAM_DURATION_SECONDS