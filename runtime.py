"""在线执行：Resolve，以及带恢复记录的调度循环。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .registry import Registry
from .rules import canonicalize, serialize
from .structs import Feedback, GroundAction, Rule, WorldState
from .trivalent import Tri, conditions_hold


@dataclass
class Support:
    canon: str
    rule: Rule
    binding: dict
    step_index: int
    action: GroundAction
    verifier_id: str
    effect_id: str
    effect_args: tuple[str, ...]


@dataclass
class Resumption:
    canon: str
    rule: Rule
    binding: dict
    stage: int
    final_action: GroundAction


@dataclass
class RunResult:
    success: bool
    score: float | None
    termination: str
    steps: int
    requests: int
    precall: int
    repairs: int
    post_call_same: int
    rejections: int
    rule_actions: int
    confirmed: int
    aborted: int
    actions: tuple[GroundAction, ...]
    history: tuple[tuple[GroundAction, Feedback], ...] = ()


def freeze_binding(binding: dict[str, str]) -> tuple:
    return tuple(sorted(binding.items()))


def prepare_library(rules, registry: Registry) -> list[Rule]:
    prepared = []
    seen = set()
    for rule in rules:
        checked, _ = canonicalize(rule, registry)
        text = serialize(checked)
        if text not in seen:
            seen.add(text)
            prepared.append(checked)
    return prepared


def resumption_ok(resumption: Resumption, registry: Registry, state: WorldState) -> bool:
    if not registry.binding_still_valid(resumption.rule, resumption.binding, state):
        return False
    step = resumption.rule.program[resumption.stage]
    return registry.stage_status(step, resumption.binding, state) is Tri.TRUE


def _disabled(disabled, canon, binding, rule, state, registry) -> bool:
    fields = registry.watched_fields(rule, binding, state)
    return (canon, freeze_binding(binding), fields) in disabled


def _support(rule, canon, binding, step_index, action, registry: Registry) -> Support:
    verifier_id = rule.verifiers[step_index]
    verifier = registry.verifiers[verifier_id]
    template = registry.templates[action.tool]
    effect_args = tuple(action.args[index] for index in template.effect_arg_index)
    return Support(
        canon,
        rule,
        dict(binding),
        step_index,
        action,
        verifier_id,
        verifier.effect_id,
        effect_args,
    )


def compatible(records: list[Support]) -> bool:
    keys = {(item.verifier_id, item.effect_id, item.effect_args) for item in records}
    return len(keys) == 1


def rejection_fires(rules, registry, state, action, unknown_as_true: bool) -> bool:
    context = state.with_examined(action)
    for rule in rules:
        if rule.tau != "reject":
            continue
        binding = registry.bind(rule, context)
        if binding is None:
            continue
        grounded = registry.ground_program(rule, binding)
        if len(grounded) != 1 or grounded[0] != action:
            continue
        values = registry.eval_conditions(rule, binding, context)
        if not conditions_hold(values, unknown_as_true):
            continue
        verdict = registry.checkers[rule.verifiers[0]].fn(context, binding, action)
        if verdict is Tri.TRUE:
            return True
    return False


def resolve(
    rules,
    registry: Registry,
    state: WorldState,
    proposal: GroundAction | None,
    resumptions: list[Resumption],
    rejected,
    disabled,
    unknown_as_true: bool = False,
):
    """返回唯一且校验器兼容的动作。本函数不向环境提交动作，也不推进恢复记录。"""
    supports: list[Support] = []
    busy = {(item.canon, freeze_binding(item.binding)) for item in resumptions}
    for resumption in resumptions:
        if proposal is not None and resumption.final_action != proposal:
            continue
        if not resumption_ok(resumption, registry, state):
            continue
        if _disabled(
            disabled,
            resumption.canon,
            resumption.binding,
            resumption.rule,
            state,
            registry,
        ):
            continue
        grounded = registry.ground_program(resumption.rule, resumption.binding)
        supports.append(
            _support(
                resumption.rule,
                resumption.canon,
                resumption.binding,
                resumption.stage,
                grounded[resumption.stage],
                registry,
            )
        )
    for rule in rules:
        if rule.tau != "exec":
            continue
        binding = registry.bind(rule, state)
        if binding is None:
            continue
        canon = serialize(rule)
        if (canon, freeze_binding(binding)) in busy:
            continue
        if _disabled(disabled, canon, binding, rule, state, registry):
            continue
        if not conditions_hold(registry.eval_conditions(rule, binding, state), unknown_as_true):
            continue
        if registry.stage_status(rule.program[0], binding, state) is not Tri.TRUE:
            continue
        grounded = registry.ground_program(rule, binding)
        if proposal is not None and grounded[-1] != proposal:
            continue
        supports.append(_support(rule, canon, binding, 0, grounded[0], registry))

    rejected_set = set(rejected)
    examined = []
    seen = set()
    for record in supports:
        if record.action not in seen:
            examined.append(record.action)
            seen.add(record.action)
    if proposal is not None and proposal not in seen:
        examined.append(proposal)
    for action in examined:
        if rejection_fires(rules, registry, state, action, unknown_as_true):
            rejected_set.add(action)

    available: dict[GroundAction, list[Support]] = {}
    for record in supports:
        if record.action in rejected_set:
            continue
        available.setdefault(record.action, []).append(record)
    rejected_list = list(rejected_set)
    if len(available) == 1:
        action, records = next(iter(available.items()))
        if compatible(records):
            return action, records, rejected_list
    return None, [], rejected_list


def _valid_action(action, registry: Registry) -> bool:
    if not isinstance(action, GroundAction):
        return False
    template = registry.templates.get(action.tool)
    if template is None:
        return False
    return len(action.args) == len(template.param_types) and action.arg_types == template.param_types


def _judge(records: list[Support], action, feedback: Feedback, stepwise: bool) -> Tri:
    if not stepwise:
        return Tri.TRUE
    if any(record.action != action for record in records):
        return Tri.FALSE
    verdicts = []
    for record in records:
        matched = (
            feedback.status == "confirm"
            and feedback.effect_id == record.effect_id
            and tuple(feedback.effect_args) == tuple(record.effect_args)
        )
        if matched:
            verdicts.append(Tri.TRUE)
        elif feedback.status in {"reject", "confirm"}:
            verdicts.append(Tri.FALSE)
        else:
            verdicts.append(Tri.UNKNOWN)
    if any(item is Tri.FALSE for item in verdicts):
        return Tri.FALSE
    if any(item is Tri.UNKNOWN for item in verdicts):
        return Tri.UNKNOWN
    return Tri.TRUE


def _advance(records: list[Support], registry: Registry) -> list[Resumption]:
    pending = []
    for record in records:
        nxt = record.step_index + 1
        if nxt >= len(record.rule.program):
            continue
        grounded = registry.ground_program(record.rule, record.binding)
        pending.append(
            Resumption(record.canon, record.rule, dict(record.binding), nxt, grounded[-1])
        )
    return pending


def run_task(
    env,
    policy,
    rules,
    registry: Registry,
    *,
    rule_budget: int,
    proposal_cap: int,
    step_limit: int,
    unknown_as_true: bool = False,
    stepwise: bool = True,
    mode: str = "rules",
) -> RunResult:
    library = [] if mode != "rules" else prepare_library(rules, registry)
    state = env.reset()
    history = []
    resumptions: list[Resumption] = []
    disabled = set()
    budget_used = 0
    force_model = False
    requests = precall = repairs = post_call_same = 0
    rejections = rule_actions = confirmed = aborted = 0
    actions = []
    steps = 0
    unresolved = False
    success = False
    score = None

    while steps < step_limit:
        action = None
        supports: list[Support] = []
        by_rule = False
        clear_resumptions = False
        if mode == "rules":
            if any(not resumption_ok(item, registry, state) for item in resumptions):
                resumptions = []
                force_model = True
            if budget_used >= rule_budget:
                resumptions = []
            rejected: list[GroundAction] = []
            if (not force_model) and budget_used < rule_budget:
                before = set(rejected)
                action, supports, rejected = resolve(
                    library,
                    registry,
                    state,
                    None,
                    resumptions,
                    rejected,
                    disabled,
                    unknown_as_true,
                )
                rejections += len(set(rejected) - before)
                if action is not None:
                    by_rule = True
                    precall += 1
            if action is None:
                chosen = False
                for _ in range(proposal_cap):
                    proposal = policy.propose(state.goal_dict(), list(history), list(rejected), state)
                    requests += 1
                    if not _valid_action(proposal, registry):
                        continue
                    before = set(rejected)
                    alternative, alternative_supports, rejected = resolve(
                        library,
                        registry,
                        state,
                        proposal,
                        resumptions,
                        rejected,
                        disabled,
                        unknown_as_true,
                    )
                    rejections += len(set(rejected) - before)
                    if (
                        (not force_model)
                        and budget_used < rule_budget
                        and alternative is not None
                    ):
                        action = alternative
                        supports = alternative_supports
                        by_rule = True
                        if alternative != proposal:
                            repairs += 1
                        else:
                            post_call_same += 1
                        chosen = True
                        break
                    if proposal in set(rejected):
                        continue
                    action = proposal
                    supports = []
                    by_rule = False
                    clear_resumptions = True
                    chosen = True
                    break
                if not chosen:
                    unresolved = True
                    break
        else:
            rejected = []
            chosen = False
            for _ in range(proposal_cap):
                proposal = policy.propose(state.goal_dict(), list(history), list(rejected), state)
                requests += 1
                if not _valid_action(proposal, registry):
                    continue
                if mode == "interface":
                    reason = registry.interface_reject_reason(state, proposal)
                    if reason is not None:
                        if proposal not in rejected:
                            rejected.append(proposal)
                            rejections += 1
                        continue
                action = proposal
                chosen = True
                break
            if not chosen:
                unresolved = True
                break

        if clear_resumptions:
            resumptions = []
        result = env.step(action)
        state = result.state
        history.append((action, result.feedback))
        actions.append(action)
        steps += 1
        success = result.success
        score = result.score if result.score is not None else score
        force_model = False
        if by_rule:
            budget_used += 1
            rule_actions += 1
            verdict = _judge(supports, action, result.feedback, stepwise)
            if verdict is Tri.TRUE:
                resumptions = _advance(supports, registry)
                confirmed += 1
            else:
                resumptions = []
                for record in supports:
                    fields = registry.watched_fields(record.rule, record.binding, state)
                    disabled.add((record.canon, freeze_binding(record.binding), fields))
                force_model = True
                aborted += 1
        if result.done:
            break

    if unresolved:
        termination = "unresolved_conflict"
    elif success:
        termination = "success"
    elif steps >= step_limit:
        termination = "timeout"
    else:
        termination = "fail"
    return RunResult(
        success,
        score,
        termination,
        steps,
        requests,
        precall,
        repairs,
        post_call_same,
        rejections,
        rule_actions,
        confirmed,
        aborted,
        tuple(actions),
        tuple(history),
    )
