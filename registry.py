"""固定领域接口：谓词、动作模板、阶段前提和校验器。"""

from __future__ import annotations

from dataclasses import dataclass

from .structs import (
    ActionStep,
    Atom,
    BindingSource,
    GroundAction,
    Rule,
    Term,
    WorldState,
)
from .trivalent import Tri, conjunction


@dataclass(frozen=True)
class Predicate:
    name: str
    arg_types: tuple[str, ...]
    fn: object
    fields: object
    order: int


@dataclass(frozen=True)
class Verifier:
    name: str
    effect_id: str


@dataclass(frozen=True)
class Template:
    tool: str
    param_types: tuple[str, ...]
    effect_id: str
    effect_arg_index: tuple[int, ...]
    verifier_id: str
    stage: tuple[tuple[str, tuple[int, ...]], ...]
    allowed_verifiers: tuple[str, ...]


@dataclass(frozen=True)
class Checker:
    name: str
    effect_id: str
    fn: object
    fields: object


class Registry:
    def __init__(
        self,
        domain: str,
        min_conditions: int = 1,
        max_conditions: int = 3,
        max_program_length: int = 2,
    ):
        self.domain = domain
        self.min_conditions = min_conditions
        self.max_conditions = max_conditions
        self.max_program_length = max_program_length
        self.predicates: dict[str, Predicate] = {}
        self.templates: dict[str, Template] = {}
        self.verifiers: dict[str, Verifier] = {}
        self.checkers: dict[str, Checker] = {}

    def add_predicate(self, name, arg_types, fn, fields) -> None:
        self.predicates[name] = Predicate(
            name, tuple(arg_types), fn, fields, len(self.predicates)
        )

    def add_verifier(self, name: str, effect_id: str) -> None:
        self.verifiers[name] = Verifier(name, effect_id)

    def add_template(
        self,
        tool,
        param_types,
        effect_id,
        effect_arg_index,
        verifier_id,
        stage=(),
        allowed_verifiers=None,
    ) -> None:
        if verifier_id not in self.verifiers:
            self.add_verifier(verifier_id, effect_id)
        allowed = tuple(allowed_verifiers or (verifier_id,))
        self.templates[tool] = Template(
            tool,
            tuple(param_types),
            effect_id,
            tuple(effect_arg_index),
            verifier_id,
            tuple(stage),
            allowed,
        )

    def add_checker(self, name, effect_id, fn, fields) -> None:
        self.checkers[name] = Checker(name, effect_id, fn, fields)

    def make_action(self, tool: str, args) -> GroundAction:
        template = self.templates[tool]
        values = tuple(args)
        if len(values) != len(template.param_types):
            raise ValueError(f"{tool} 需要 {len(template.param_types)} 个参数")
        return GroundAction(tool, values, template.param_types)

    def subst(self, term: Term, binding: dict[str, str]) -> str:
        if term.kind == "const":
            return term.value
        return binding[term.value]

    def eval_atom(self, atom: Atom, binding: dict[str, str], state: WorldState) -> Tri:
        predicate = self.predicates[atom.predicate]
        concrete = tuple(self.subst(term, binding) for term in atom.args)
        return predicate.fn(state, concrete)

    def eval_conditions(self, rule: Rule, binding: dict[str, str], state: WorldState):
        return tuple(self.eval_atom(atom, binding, state) for atom in rule.conditions)

    def stage_status(self, step: ActionStep, binding: dict[str, str], state: WorldState) -> Tri:
        template = self.templates[step.tool]
        args = tuple(self.subst(term, binding) for term in step.args)
        return self.stage_status_args(template, args, state)

    def stage_status_args(self, template: Template, args, state: WorldState) -> Tri:
        values = []
        for predicate_name, indexes in template.stage:
            concrete = tuple(args[index] for index in indexes)
            values.append(self.predicates[predicate_name].fn(state, concrete))
        return conjunction(values)

    def ground_program(self, rule: Rule, binding: dict[str, str]) -> tuple[GroundAction, ...]:
        grounded = []
        for step in rule.program:
            template = self.templates[step.tool]
            args = tuple(self.subst(term, binding) for term in step.args)
            grounded.append(GroundAction(step.tool, args, template.param_types))
        return tuple(grounded)

    def unique_failure(self, state: WorldState, tool: str):
        found = [item for item in state.failures if item.tool == tool]
        if len(found) != 1:
            return None
        return found[0]

    def bind(self, rule: Rule, state: WorldState) -> dict[str, str] | None:
        binding: dict[str, str] = {}
        for source in rule.bindings:
            value = self._bind_one(source, state)
            if value is None:
                return None
            if source.variable in binding and binding[source.variable] != value:
                return None
            if source.origin != "literal":
                entity = state.entity(value)
                if entity is None or entity.type_name != source.type_name:
                    return None
            binding[source.variable] = value
        expected = {source.variable for source in rule.bindings}
        if set(binding) != expected:
            return None
        return binding

    def _bind_one(self, source: BindingSource, state: WorldState) -> str | None:
        if source.origin == "action_arg":
            tool, index_text = source.detail.split(":", 1)
            failure = self.unique_failure(state, tool)
            if failure is None:
                return None
            index = int(index_text)
            if index < 0 or index >= len(failure.args):
                return None
            return failure.args[index]
        if source.origin == "visible":
            matches = []
            for entity_id in state.visible:
                entity = state.entity(entity_id)
                if entity is not None and entity.type_name == source.type_name:
                    matches.append(entity_id)
            if len(matches) != 1:
                return None
            return matches[0]
        if source.origin == "examined":
            if state.examined is None:
                return None
            index = int(source.detail)
            if index < 0 or index >= len(state.examined.args):
                return None
            return state.examined.args[index]
        if source.origin == "literal":
            return source.detail
        return None

    def binding_still_valid(self, rule: Rule, binding: dict[str, str], state: WorldState) -> bool:
        for source in rule.bindings:
            value = binding.get(source.variable)
            if value is None:
                return False
            if source.origin == "literal":
                if value != source.detail:
                    return False
                continue
            entity = state.entity(value)
            if entity is None or entity.type_name != source.type_name:
                return False
        rebound = self.bind(rule, state)
        return rebound == binding

    def binding_field_names(self, source: BindingSource) -> tuple[str, ...]:
        if source.origin == "action_arg":
            tool = source.detail.split(":", 1)[0]
            return (f"failures:{tool}",)
        if source.origin == "visible":
            return (f"visible:{source.type_name}",)
        if source.origin == "examined":
            return ("examined",)
        return ()

    def watched_fields(self, rule: Rule, binding: dict[str, str], state: WorldState):
        names = set()
        for atom in rule.conditions:
            args = tuple(self.subst(term, binding) for term in atom.args)
            names.update(self.predicates[atom.predicate].fields(args))
        for source in rule.bindings:
            names.update(self.binding_field_names(source))
        for step in rule.program:
            template = self.templates[step.tool]
            args = tuple(self.subst(term, binding) for term in step.args)
            for predicate_name, indexes in template.stage:
                concrete = tuple(args[index] for index in indexes)
                names.update(self.predicates[predicate_name].fields(concrete))
        return tuple((name, read_field(state, name)) for name in sorted(names))

    def interface_reject_reason(self, state: WorldState, action: GroundAction) -> str | None:
        """只做接口检查的对照：阶段前提和冲突检查，不提供替代动作。"""
        template = self.templates.get(action.tool)
        if template is None or len(action.args) != len(template.param_types):
            return "invalid_action"
        stage = self.stage_status_args(template, action.args, state)
        if stage is Tri.FALSE:
            return "stage_false"
        if stage is Tri.UNKNOWN:
            return "stage_unknown"
        examined = state.with_examined(action)
        for checker in self.checkers.values():
            verdict = checker.fn(examined, {}, action)
            if verdict is Tri.TRUE:
                return "conflict"
        return None


def read_field(state: WorldState, name: str) -> str:
    if name.startswith("entity:"):
        _, entity_id, attr = name.split(":", 2)
        entity = state.entity(entity_id)
        if entity is None:
            return ""
        return entity.get(attr, "")
    if name.startswith("fail:"):
        _, tool, left, right = name.split(":", 3)
        reasons = [
            item.reason
            for item in state.failures
            if item.tool == tool and item.args == (left, right)
        ]
        return ",".join(reasons)
    if name.startswith("failures:"):
        tool = name.split(":", 1)[1]
        parts = [
            f"{','.join(item.args)}:{item.reason}"
            for item in state.failures
            if item.tool == tool
        ]
        return "|".join(parts)
    if name.startswith("visible:"):
        type_name = name.split(":", 1)[1]
        ids = [
            entity_id
            for entity_id in state.visible
            if state.entity(entity_id) is not None
            and state.entity(entity_id).type_name == type_name
        ]
        return ",".join(ids)
    if name.startswith("goal:"):
        key = name.split(":", 1)[1]
        return state.goal_dict().get(key, "")
    if name == "examined":
        if state.examined is None:
            return ""
        return state.examined.format()
    return ""


def flag_predicate(attr: str):
    """读取实体上的 true/false 属性。缺失时返回未知。"""

    def evaluate(state: WorldState, args):
        entity = state.entity(args[0])
        if entity is None:
            return Tri.UNKNOWN
        raw = entity.get(attr, "")
        if raw == "true":
            return Tri.TRUE
        if raw == "false":
            return Tri.FALSE
        return Tri.UNKNOWN

    def fields(args):
        return (f"entity:{args[0]}:{attr}",)

    return evaluate, fields
