"""生成与修订提示。损失只计算规则输出。"""

from __future__ import annotations

GENERATION_INSTRUCTION = """根据给定的领域接口、目标局部效果和轨迹片段，输出一条规范规则。
只使用列出的谓词、动作模板、绑定来源和验证器。
启动条件不超过 3 个，执行程序不超过 2 步。
证据不足时只输出 insufficient evidence。
不要复述提示。"""

REVISION_INSTRUCTION = """根据已有规则和明确反例修订启动条件、绑定或程序。
阶段前提和验证器保持注册定义，不要改写。
修订后的规则仍使用规范文本。
证据不足时只输出 insufficient evidence。
不要复述提示。"""


def generation_prompt(domain: str, predicates, templates, effect: str, fragments: dict) -> str:
    return "\n".join(
        [
            GENERATION_INSTRUCTION,
            f"domain: {domain}",
            f"predicates: {', '.join(predicates)}",
            f"templates: {', '.join(templates)}",
            f"effect: {effect}",
            f"positive: {fragments.get('positive', [])}",
            f"counterexample: {fragments.get('counterexample', [])}",
            f"unknown: {fragments.get('unknown', [])}",
        ]
    )


def revision_prompt(domain: str, rule_text: str, counterexamples) -> str:
    groups = ", ".join(str(item) for item in counterexamples)
    return "\n".join(
        [
            REVISION_INSTRUCTION,
            f"domain: {domain}",
            f"rule: {rule_text}",
            f"counterexample: {groups}",
        ]
    )
