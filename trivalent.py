"""三值逻辑。条件合取取 true、false 或 unknown。"""

from __future__ import annotations

from enum import Enum


class Tri(Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def conjunction(values) -> Tri:
    """全部为真才为真；任一为假则为假；其余为未知。空合取视为真。"""
    saw_unknown = False
    for value in values:
        if value is Tri.FALSE:
            return Tri.FALSE
        if value is Tri.UNKNOWN:
            saw_unknown = True
    if saw_unknown:
        return Tri.UNKNOWN
    return Tri.TRUE


def conditions_hold(values, unknown_as_true: bool = False) -> bool:
    """执行规则只有在启动条件成立时才能开始。

    主配置把未知当作不成立。消融实验里可以把未知当作满足，假值仍然阻断。
    """
    if unknown_as_true:
        return all(value is not Tri.FALSE for value in values)
    return all(value is Tri.TRUE for value in values)
