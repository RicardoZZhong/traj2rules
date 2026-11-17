"""由运行记录、规则库和探测标注计算审稿要求的统计量。"""

from __future__ import annotations


def cost_per_success(total_cost: float, successes: float):
    if successes <= 0:
        return None
    return total_cost / successes


def breakeven_attempts(offline_delta: float, online_baseline: float, online_method: float):
    """在线差额不是正数时，不给出回本尝试数。"""
    gap = online_baseline - online_method
    if offline_delta <= 0 or gap <= 0:
        return None
    return offline_delta / gap


def support_failure_bound(support: int, alpha: float = 0.05):
    """无反例且有 S₊ 个支持组时，组反例率的 1-alpha 上界。"""
    if support <= 0:
        return None
    return 1 - alpha ** (1 / support)


def false_trigger_rates(triggered_negative: int, query_groups: int, known_negative: int, decisive: int):
    def ratio(numerator, denominator):
        if denominator <= 0:
            return None
        return numerator / denominator

    return {
        "incidence_per_query_group": ratio(triggered_negative, query_groups),
        "among_known_negatives": ratio(triggered_negative, known_negative),
        "among_decisive_triggers": ratio(triggered_negative, decisive),
    }


def count_request_reasons(events) -> dict:
    counts = {"initial_proposal": 0, "format_retry": 0, "conflict_reselection": 0}
    for event in events:
        reason = event["reason"]
        counts[reason] = counts.get(reason, 0) + 1
    counts["total"] = len(events)
    counts["submitted"] = sum(1 for event in events if event.get("submitted"))
    counts["balanced"] = counts["total"] == sum(
        counts[name] for name in ("initial_proposal", "format_retry", "conflict_reselection")
    )
    return counts


def action_confirmation_rate(confirmed: int, rule_actions: int):
    if rule_actions <= 0:
        return None
    return confirmed / rule_actions


def program_completion_rate(completed: int, started: int):
    if started <= 0:
        return None
    return completed / started
