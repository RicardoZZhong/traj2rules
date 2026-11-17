"""按程序标注轨迹证据，并在任务组内汇总。

组标签：组内只要有明确反例就是负例；否则有正例就是正例；其余为未知。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from .registry import Registry
from .rules import canonicalize
from .structs import (
    Episode,
    ExecutedStep,
    Feedback,
    GroundAction,
    Rule,
    SavedState,
)
from .trivalent import Tri, conditions_hold


class Label(Enum):
    POSITIVE = "+"
    NEGATIVE = "-"
    UNKNOWN = "?"


@dataclass(frozen=True)
class Recovery:
    failed: GroundAction
    preparatory: GroundAction
    retry: GroundAction
    effect_id: str | None


@dataclass(frozen=True)
class ScoredRule:
    rule: Rule
    canon: str
    positive_groups: frozenset[str]
    negative_groups: frozenset[str]
    unknown_groups: frozenset[str]

    @property
    def support(self) -> int:
        return len(self.positive_groups)


def aggregate(labels) -> Label:
    saw_positive = False
    for label in labels:
        if label is Label.NEGATIVE:
            return Label.NEGATIVE
        if label is Label.POSITIVE:
            saw_positive = True
    if saw_positive:
        return Label.POSITIVE
    return Label.UNKNOWN


def merge_scored(left: ScoredRule, right: ScoredRule) -> ScoredRule:
    negative = left.negative_groups | right.negative_groups
    positive = (left.positive_groups | right.positive_groups) - negative
    unknown = (left.unknown_groups | right.unknown_groups) - negative - positive
    return ScoredRule(left.rule, left.canon, positive, negative, unknown)


def extract_recovery_programs(steps: list[tuple[GroundAction, Feedback]]) -> list[Recovery]:
    """失败动作之后紧跟准备动作，再用原参数重试并确认效果。"""
    found = []
    for index in range(len(steps) - 2):
        failed, failed_feedback = steps[index]
        prep, _prep_feedback = steps[index + 1]
        retry, retry_feedback = steps[index + 2]
        if failed_feedback.status != "reject":
            continue
        if prep.tool == failed.tool:
            continue
        if retry.tool != failed.tool or retry.args != failed.args:
            continue
        if len(failed.arg_types) != len(set(failed.arg_types)):
            continue
        if retry_feedback.status != "confirm":
            continue
        found.append(
            Recovery(failed, prep, retry, retry_feedback.effect_id)
        )
    return found


def score_rule(
    rule: Rule,
    episodes: list[Episode],
    registry: Registry,
    saved_states: list[SavedState] | None = None,
    replay_fn=None,
    cache: dict | None = None,
) -> ScoredRule:
    rule, canon = canonicalize(rule, registry)
    saved_states = saved_states or []
    cache = cache if cache is not None else {}
    grouped = defaultdict(list)
    for episode in episodes:
        grouped[episode.group_id].append(label_episode(rule, episode, registry))
    group_ids = set(grouped) | {item.group_id for item in saved_states}
    positive, negative, unknown = set(), set(), set()
    for group_id in group_ids:
        label = aggregate(grouped.get(group_id, []))
        if (
            label is Label.UNKNOWN
            and replay_fn is not None
            and rule.tau == "exec"
        ):
            replayed = _replay_group(
                rule, canon, group_id, registry, saved_states, replay_fn, cache
            )
            if replayed is not None:
                label = replayed
        if label is Label.POSITIVE:
            positive.add(group_id)
        elif label is Label.NEGATIVE:
            negative.add(group_id)
        else:
            unknown.add(group_id)
    return ScoredRule(
        rule, canon, frozenset(positive), frozenset(negative), frozenset(unknown)
    )


def label_episode(rule: Rule, episode: Episode, registry: Registry) -> Label:
    if rule.tau == "reject":
        return _label_rejection(rule, episode, registry)
    binding = registry.bind(rule, episode.state)
    if binding is None:
        return Label.UNKNOWN
    values = registry.eval_conditions(rule, binding, episode.state)
    if not conditions_hold(values, False):
        return Label.UNKNOWN
    grounded = registry.ground_program(rule, binding)
    if len(episode.steps) < len(grounded):
        return Label.UNKNOWN
    matched = []
    for spec, executed in zip(grounded, episode.steps):
        if executed.action != spec:
            return Label.UNKNOWN
        matched.append(executed)
    return _label_feedback(matched, registry)


def _label_feedback(matched: list[ExecutedStep], registry: Registry) -> Label:
    saw_unknown = False
    for executed in matched:
        template = registry.templates[executed.action.tool]
        effect_args = tuple(executed.action.args[index] for index in template.effect_arg_index)
        feedback = executed.feedback
        if feedback.status == "not_executed":
            return Label.UNKNOWN
        confirmed = (
            feedback.status == "confirm"
            and feedback.effect_id == template.effect_id
            and tuple(feedback.effect_args) == effect_args
        )
        if confirmed:
            continue
        if feedback.status == "reject" or feedback.status == "confirm":
            return Label.NEGATIVE
        saw_unknown = True
    return Label.UNKNOWN if saw_unknown else Label.POSITIVE


def _label_rejection(rule: Rule, episode: Episode, registry: Registry) -> Label:
    action = episode.candidate_action
    if action is None:
        return Label.UNKNOWN
    state = episode.state.with_examined(action)
    binding = registry.bind(rule, state)
    if binding is None:
        return Label.UNKNOWN
    grounded = registry.ground_program(rule, binding)
    if len(grounded) != 1 or grounded[0] != action:
        return Label.UNKNOWN
    if not conditions_hold(registry.eval_conditions(rule, binding, state), False):
        return Label.UNKNOWN
    verdict = registry.checkers[rule.verifiers[0]].fn(state, binding, action)
    if verdict is Tri.TRUE:
        return Label.POSITIVE
    if verdict is Tri.FALSE:
        return Label.NEGATIVE
    return Label.UNKNOWN


def _start_applicable(rule: Rule, state, registry: Registry) -> bool:
    binding = registry.bind(rule, state)
    if binding is None:
        return False
    if not conditions_hold(registry.eval_conditions(rule, binding, state), False):
        return False
    return registry.stage_status(rule.program[0], binding, state) is Tri.TRUE


def _replay_group(rule, canon, group_id, registry, saved_states, replay_fn, cache):
    candidates = [
        item
        for item in saved_states
        if item.group_id == group_id and _start_applicable(rule, item.state, registry)
    ]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda item: item.order)
    key = (canon, group_id, chosen.order)
    if key not in cache:
        binding = registry.bind(rule, chosen.state)
        actions = registry.ground_program(rule, binding)
        cache[key] = tuple(replay_fn(chosen.state, actions))
    feedbacks = cache[key]
    if len(feedbacks) != len(rule.program):
        return Label.UNKNOWN
    matched = [
        ExecutedStep(action, feedback)
        for action, feedback in zip(registry.ground_program(rule, registry.bind(rule, chosen.state)), feedbacks)
    ]
    return _label_feedback(matched, registry)


def ranking_key(scored: ScoredRule) -> tuple:
    """降序 ρ=(S₊, −|I|, −|C|, −canon) 的升序等价键。

    支持组更多、程序更短、条件更少者优先。规范文本只在前三项完全相同时打破平局。
    """
    return (
        -scored.support,
        len(scored.rule.program),
        len(scored.rule.conditions),
        scored.canon,
    )
