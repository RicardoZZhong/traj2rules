"""按任务组标识的 SHA-256 顺序切分数据。测试池先剔除，余量不使用。"""

from __future__ import annotations

import hashlib

from .config import PARTITION_ORDER


def canonical_group_id(*parts: str) -> str:
    return "\n".join(part.strip() for part in parts)


def partition_groups(group_ids, counts: dict[str, int], test_ids=()) -> dict[str, list]:
    blocked = set(test_ids)
    remaining = [group_id for group_id in group_ids if group_id not in blocked]
    remaining.sort(
        key=lambda group_id: (
            hashlib.sha256(group_id.encode("utf-8")).hexdigest(),
            group_id,
        )
    )
    assigned = {}
    cursor = 0
    for name in PARTITION_ORDER:
        count = counts[name]
        assigned[name] = remaining[cursor : cursor + count]
        cursor += count
    assigned["unused"] = remaining[cursor:]
    return assigned
