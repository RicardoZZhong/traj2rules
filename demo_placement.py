"""放置任务：先修订规则，再在线接管。"""

from __future__ import annotations

from .config import SEARCH
from .domains.placement import (
    PlacementEnv,
    build_registry,
    in_effect,
    make_recovery_rule,
    sample_episodes,
)
from .library import ListGenerator, construct_library
from .rules import canonicalize, serialize
from .runtime import run_task


class _NoModel:
    def propose(self, goal, history, rejected, state):
        raise AssertionError("物体已拿住时，这一步应由规则接管，不应调用模型")


class _AlwaysMove:
    def __init__(self, registry):
        self.action = registry.make_action("move", ("thermometer", "freezer"))
        self.calls = 0

    def propose(self, goal, history, rejected, state):
        self.calls += 1
        return self.action


def build_placement_library():
    registry = build_registry()
    _without_held, without_text = canonicalize(make_recovery_rule(False), registry)
    _with_held, with_text = canonicalize(make_recovery_rule(True), registry)
    generator = ListGenerator([without_text, "??", without_text], [[with_text]])
    built = construct_library(
        registry,
        sample_episodes(),
        [in_effect()],
        generator,
        SEARCH,
    )
    return registry, built


def run_held_example():
    registry, built = build_placement_library()
    result = run_task(
        PlacementEnv(held=True),
        _NoModel(),
        built.rules,
        registry,
        rule_budget=12,
        proposal_cap=SEARCH.proposal_cap,
        step_limit=8,
    )
    return built, result


def run_unheld_example():
    registry, built = build_placement_library()
    policy = _AlwaysMove(registry)
    result = run_task(
        PlacementEnv(held=False),
        policy,
        built.rules,
        registry,
        rule_budget=12,
        proposal_cap=SEARCH.proposal_cap,
        step_limit=2,
    )
    return result, policy.calls


def main() -> None:
    built, held = run_held_example()
    unheld, calls = run_unheld_example()
    print("放置：容器关着，物体已经拿住。")
    print(f"库中规则数：{len(built.rules)}")
    print(serialize(built.rules[0]))
    print("在线动作：" + " -> ".join(action.format() for action in held.actions))
    print(
        f"模型请求 {held.requests}，规则接管 {held.precall}，"
        f"确认 {held.confirmed}，结果 {held.termination}"
    )
    print("物体没有拿住时，规则不接管。")
    print("在线动作：" + " -> ".join(action.format() for action in unheld.actions))
    print(f"模型请求 {calls}，规则动作 {unheld.rule_actions}，结果 {unheld.termination}")


if __name__ == "__main__":
    main()
