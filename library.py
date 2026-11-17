"""离线候选生成、证据检查和确定性规则库选择。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations, product

from .config import SEARCH, SearchConfig
from .evidence import ScoredRule, merge_scored, ranking_key, score_rule
from .registry import Registry
from .rules import canonicalize, effect_key, parse_rule, serialize, typecheck
from .structs import (
    ActionStep,
    Atom,
    BindingSource,
    Episode,
    Rule,
    SavedState,
    Term,
)


@dataclass
class SelectionDecision:
    canon: str
    signature: tuple
    positive_groups: tuple[str, ...]
    negative_groups: tuple[str, ...]
    ranking: tuple
    selected: bool


@dataclass
class GroupTrace:
    effect: tuple
    used: int = 0
    malformed: int = 0
    duplicates: int = 0
    revision_calls: int = 0


@dataclass
class LibraryResult:
    rules: list[Rule]
    decisions: list[SelectionDecision]
    scored: list[ScoredRule]
    traces: list[GroupTrace] = field(default_factory=list)


class ListGenerator:
    """测试和演示用的固定候选源。输出额度由库构建过程截断。"""

    def __init__(self, initial, revisions=None):
        self.initial = list(initial)
        self.revisions = list(revisions or [])
        self.revise_calls = 0

    def generate(self, effect, limit: int):
        return list(self.initial[:limit])

    def revise(self, candidates, limit: int):
        if self.revise_calls >= len(self.revisions):
            batch = []
        else:
            batch = self.revisions[self.revise_calls]
        self.revise_calls += 1
        return list(batch[:limit])


def select_library(
    scored: list[ScoredRule],
    n_min: int = SEARCH.n_min,
    capacity: int = SEARCH.library_capacity,
) -> tuple[list[ScoredRule], list[SelectionDecision]]:
    merged: dict[str, ScoredRule] = {}
    for item in scored:
        current = merged.get(item.canon)
        merged[item.canon] = item if current is None else merge_scored(current, item)
    ranked = sorted(merged.values(), key=ranking_key)
    selected: list[ScoredRule] = []
    decisions = []
    for item in ranked:
        eligible = len(item.negative_groups) == 0 and item.support >= n_min
        take = eligible and len(selected) < capacity
        if take:
            selected.append(item)
        decisions.append(
            SelectionDecision(
                item.canon,
                effect_key(item.rule),
                tuple(sorted(item.positive_groups)),
                tuple(sorted(item.negative_groups)),
                ranking_key(item),
                take,
            )
        )
    return selected, decisions


def construct_library(
    registry: Registry,
    episodes: list[Episode],
    effects: list[tuple],
    generator,
    config: SearchConfig = SEARCH,
    saved_states: list[SavedState] | None = None,
    replay_fn=None,
) -> LibraryResult:
    """每个效果组最多 8 个初始输出和两轮修订，总计不超过 24。"""
    scored: list[ScoredRule] = []
    traces = []
    cache: dict = {}
    for effect in effects:
        group_scored, trace = _generate_group(
            registry,
            episodes,
            effect,
            generator,
            config,
            saved_states,
            replay_fn,
            cache,
        )
        scored.extend(group_scored)
        traces.append(trace)
    chosen, decisions = select_library(scored, config.n_min, config.library_capacity)
    return LibraryResult([item.rule for item in chosen], decisions, scored, traces)


def _generate_group(
    registry,
    episodes,
    effect,
    generator,
    config,
    saved_states,
    replay_fn,
    cache,
):
    trace = GroupTrace(effect)
    pool: dict[str, ScoredRule] = {}
    outputs = list(generator.generate(effect, config.outputs_per_round))
    rounds = config.revision_rounds + 1
    for round_index in range(rounds):
        counted = []
        for raw in outputs:
            if trace.used >= config.max_outputs_per_group:
                break
            trace.used += 1
            counted.append(raw)
        current: dict[str, Rule] = {}
        for raw in counted:
            rule = _accept(raw, registry, effect)
            if rule is None:
                trace.malformed += 1
                continue
            rule, canon = canonicalize(rule, registry)
            if effect_key(rule) != effect:
                trace.malformed += 1
                continue
            if canon in current:
                trace.duplicates += 1
            current[canon] = rule
        round_bad = []
        for canon, rule in current.items():
            scored = score_rule(
                rule,
                episodes,
                registry,
                saved_states=saved_states,
                replay_fn=replay_fn,
                cache=cache,
            )
            existing = pool.get(canon)
            pool[canon] = scored if existing is None else merge_scored(existing, scored)
            if pool[canon].negative_groups:
                round_bad.append(pool[canon])
        if round_index == config.revision_rounds:
            break
        if round_bad and trace.used < config.max_outputs_per_group:
            trace.revision_calls += 1
            outputs = list(generator.revise(round_bad, config.outputs_per_round))
        else:
            outputs = []
    return list(pool.values()), trace


def _accept(raw, registry: Registry, effect) -> Rule | None:
    if isinstance(raw, Rule):
        if raw.domain != registry.domain or not typecheck(raw, registry):
            return None
        return raw
    if not isinstance(raw, str):
        return None
    return parse_rule(raw, registry)


def library_from_enumeration(
    registry: Registry,
    episodes: list[Episode],
    effects: list[tuple],
    config: SearchConfig = SEARCH,
    saved_states: list[SavedState] | None = None,
    replay_fn=None,
) -> tuple[list[ScoredRule], list[SelectionDecision]]:
    """不使用生成器，在同一注册表上枚举不超过 m 个条件和 ell 步的程序。"""
    cache: dict = {}
    scored = []
    for effect in effects:
        if effect[1] != "exec":
            continue
        for rule in enumerate_rules(registry, effect, config):
            scored.append(
                score_rule(
                    rule,
                    episodes,
                    registry,
                    saved_states=saved_states,
                    replay_fn=replay_fn,
                    cache=cache,
                )
            )
    return select_library(scored, config.n_min, config.library_capacity)


def enumerate_rules(registry: Registry, effect: tuple, config: SearchConfig = SEARCH) -> list[Rule]:
    domain, tau, effect_id, arg_specs = effect
    if tau != "exec" or domain != registry.domain:
        return []
    variables, effect_terms, by_type = _variables(arg_specs)
    programs = []
    for template in registry.templates.values():
        if template.effect_id != effect_id:
            continue
        final_step = _fill_template(template, effect_terms, by_type, strict_effect=True)
        if final_step is None:
            continue
        programs.append((final_step,))
        if config.max_program_length < 2:
            continue
        for prefix in registry.templates.values():
            prefix_step = _fill_template(prefix, effect_terms, by_type, strict_effect=False)
            if prefix_step is None:
                continue
            programs.append((prefix_step, final_step))
    rules = []
    seen = set()
    for program in programs:
        final_step = program[-1]
        bindings = _bindings_for(variables, final_step)
        verifiers = tuple(registry.templates[step.tool].verifier_id for step in program)
        final_template = registry.templates[final_step.tool]
        effect_args = tuple(final_step.args[index] for index in final_template.effect_arg_index)
        for conditions in _condition_subsets(registry, by_type, config.max_conditions):
            rule = Rule(
                conditions,
                bindings,
                program,
                verifiers,
                "exec",
                registry.domain,
                final_template.effect_id,
                effect_args,
            )
            if not typecheck(rule, registry):
                continue
            canon_rule, text = canonicalize(rule, registry)
            if text not in seen:
                seen.add(text)
                rules.append(canon_rule)
    rules.sort(key=serialize)
    return rules


def enumerate_rejection_rules(
    registry: Registry,
    tool: str,
    checker_name: str,
    config: SearchConfig = SEARCH,
) -> list[Rule]:
    template = registry.templates[tool]
    by_type = defaultdict(list)
    args = []
    counts = defaultdict(int)
    for type_name in template.param_types:
        name = f"{type_name}{counts[type_name]}"
        counts[type_name] += 1
        term = Term("var", name, type_name)
        args.append(term)
        by_type[type_name].append(term)
    step = ActionStep(tool, tuple(args))
    bindings = tuple(
        BindingSource(term.value, term.type_name, "examined", str(index))
        for index, term in enumerate(args)
    )
    rules = []
    seen = set()
    for conditions in _condition_subsets(registry, by_type, config.max_conditions):
        rule = Rule(
            conditions,
            bindings,
            (step,),
            (checker_name,),
            "reject",
            registry.domain,
            registry.checkers[checker_name].effect_id,
            tuple(args),
        )
        if not typecheck(rule, registry):
            continue
        canon_rule, text = canonicalize(rule, registry)
        if text not in seen:
            seen.add(text)
            rules.append(canon_rule)
    rules.sort(key=serialize)
    return rules


def _variables(arg_specs):
    counts = defaultdict(int)
    by_type = defaultdict(list)
    variables = []
    effect_terms = []
    for spec in arg_specs:
        if spec[0] == "const":
            effect_terms.append(Term("const", spec[2], spec[1]))
            continue
        type_name = spec[1]
        term = Term("var", f"{type_name}{counts[type_name]}", type_name)
        counts[type_name] += 1
        variables.append(term)
        effect_terms.append(term)
        by_type[type_name].append(term)
    return variables, effect_terms, by_type


def _fill_template(template, effect_terms, by_type, strict_effect: bool):
    params = [None] * len(template.param_types)
    if strict_effect:
        if len(template.effect_arg_index) != len(effect_terms):
            return None
        for effect_index, param_index in enumerate(template.effect_arg_index):
            term = effect_terms[effect_index]
            if template.param_types[param_index] != term.type_name:
                return None
            params[param_index] = term
    for index, type_name in enumerate(template.param_types):
        if params[index] is not None:
            continue
        choices = by_type.get(type_name, [])
        if len(choices) != 1:
            return None
        params[index] = choices[0]
    if any(item is None for item in params):
        return None
    return ActionStep(template.tool, tuple(params))


def _bindings_for(variables, final_step: ActionStep):
    bindings = []
    for term in variables:
        indexes = [
            index
            for index, arg in enumerate(final_step.args)
            if arg.kind == "var" and arg.value == term.value
        ]
        if len(indexes) == 1:
            bindings.append(
                BindingSource(
                    term.value, term.type_name, "action_arg", f"{final_step.tool}:{indexes[0]}"
                )
            )
        else:
            bindings.append(
                BindingSource(term.value, term.type_name, "visible", term.type_name)
            )
    return tuple(bindings)


def _condition_subsets(registry: Registry, by_type, max_conditions: int):
    atoms = []
    for predicate in registry.predicates.values():
        pools = []
        possible = True
        for type_name in predicate.arg_types:
            choices = by_type.get(type_name, [])
            if not choices:
                possible = False
                break
            pools.append(choices)
        if not possible:
            continue
        for combo in product(*pools):
            atoms.append(Atom(predicate.name, tuple(combo)))
    subsets = []
    for size in range(1, max_conditions + 1):
        for combo in combinations(atoms, size):
            subsets.append(tuple(combo))
    return subsets
