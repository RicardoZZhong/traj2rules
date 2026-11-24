"""用枚举构建冻结规则库。不调用生成器，也不更新模型权重。"""

from __future__ import annotations

import json
from pathlib import Path

from .config import SEARCH
from .domains.placement import build_registry, in_effect, sample_episodes
from .library import enumerate_rules, library_from_enumeration


def build_enumerated_library():
    """在放置域的本地轨迹上枚举执行规则，并按证据准入冻结。"""
    registry = build_registry()
    effect = in_effect()
    candidates = enumerate_rules(registry, effect, SEARCH)
    selected, decisions = library_from_enumeration(
        registry,
        sample_episodes(),
        [effect],
        SEARCH,
    )
    return candidates, selected, decisions


def library_document(candidates, selected, decisions) -> dict:
    rules = []
    for rank, item in enumerate(selected, start=1):
        rules.append(
            {
                "rank": rank,
                "canon": item.canon,
                "support": item.support,
                "positive_groups": sorted(item.positive_groups),
                "conditions": len(item.rule.conditions),
                "program_length": len(item.rule.program),
                "program": [step.tool for step in item.rule.program],
            }
        )
    return {
        "domain": "placement",
        "method": "enumeration",
        "n_min": SEARCH.n_min,
        "capacity": SEARCH.library_capacity,
        "max_conditions": SEARCH.max_conditions,
        "max_program_length": SEARCH.max_program_length,
        "candidate_count": len(candidates),
        "admitted_count": len(selected),
        "filtered_count": sum(1 for item in decisions if not item.selected),
        "counterexample_count": sum(
            1 for item in decisions if item.negative_groups and not item.selected
        ),
        "insufficient_support_count": sum(
            1
            for item in decisions
            if not item.negative_groups and not item.selected
        ),
        "rules": rules,
    }


def write_library(document: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    candidates, selected, decisions = build_enumerated_library()
    document = library_document(candidates, selected, decisions)
    path = Path(__file__).resolve().parents[1] / "output" / "enumerated_library.json"
    write_library(document, path)
    print(
        f"枚举候选 {document['candidate_count']} 条，"
        f"准入 {document['admitted_count']} 条，"
        f"滤掉 {document['filtered_count']} 条。"
    )
    print(f"已写入 {path}")
    for rule in document["rules"]:
        print(f"{rule['rank']}. support={rule['support']} {rule['canon']}")


if __name__ == "__main__":
    main()
