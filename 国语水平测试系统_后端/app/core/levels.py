"""国语（普通话）水平等级对照。

97-100   一级甲等
92-96.9  一级乙等
87-91.9  二级甲等
80-86.9  二级乙等
70-79.9  三级甲等
60-69.9  三级乙等
60 以下  不入级
"""


def level_of(score: float | None) -> str:
    """按总分给出等级；无成绩返回空串。"""
    if score is None:
        return ""
    if score >= 97:
        return "一级甲等"
    if score >= 92:
        return "一级乙等"
    if score >= 87:
        return "二级甲等"
    if score >= 80:
        return "二级乙等"
    if score >= 70:
        return "三级甲等"
    if score >= 60:
        return "三级乙等"
    return "不入级"