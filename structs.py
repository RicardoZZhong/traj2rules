"""规则、状态和轨迹记录。结构对应 r = <C, K, I, V, tau>。"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Term:
    kind: str  # "var" 或 "const"
    value: str
    type_name: str


@dataclass(frozen=True)
class Atom:
    predicate: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class BindingSource:
    """变量可以来自动作参数、当前可见实体、字面量，或正在检查的动作。"""

    variable: str
    type_name: str
    origin: str  # action_arg, visible, literal, examined
    detail: str


@dataclass(frozen=True)
class ActionStep:
    tool: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class Rule:
    conditions: tuple[Atom, ...]
    bindings: tuple[BindingSource, ...]
    program: tuple[ActionStep, ...]
    verifiers: tuple[str, ...]
    tau: str  # exec 或 reject
    domain: str
    effect_id: str
    effect_args: tuple[Term, ...]


@dataclass(frozen=True)
class Entity:
    id: str
    type_name: str
    attrs: tuple[tuple[str, str], ...]

    def get(self, key: str, default: str = "") -> str:
        for name, value in self.attrs:
            if name == key:
                return value
        return default


def make_entity(entity_id: str, type_name: str, **attrs: str) -> Entity:
    pairs = tuple(sorted((str(key), str(value)) for key, value in attrs.items()))
    return Entity(entity_id, type_name, pairs)


@dataclass(frozen=True)
class Failure:
    tool: str
    args: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class GroundAction:
    tool: str
    args: tuple[str, ...]
    arg_types: tuple[str, ...]

    def format(self) -> str:
        return f"{self.tool}({', '.join(self.args)})"


@dataclass(frozen=True)
class Feedback:
    status: str  # confirm, reject, unknown, not_executed
    effect_id: str | None = None
    effect_args: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class WorldState:
    domain: str
    goal: tuple[tuple[str, str], ...]
    entities: tuple[Entity, ...]
    visible: tuple[str, ...]
    failures: tuple[Failure, ...] = ()
    examined: GroundAction | None = None

    def entity(self, entity_id: str) -> Entity | None:
        for item in self.entities:
            if item.id == entity_id:
                return item
        return None

    def goal_dict(self) -> dict[str, str]:
        return dict(self.goal)

    def with_examined(self, action: GroundAction | None) -> "WorldState":
        return replace(self, examined=action)


@dataclass(frozen=True)
class StepResult:
    state: WorldState
    feedback: Feedback
    done: bool
    success: bool
    score: float | None = None


@dataclass(frozen=True)
class ExecutedStep:
    action: GroundAction
    feedback: Feedback


@dataclass(frozen=True)
class Episode:
    """一条从某个状态开始的执行片段。steps[0] 紧接在 state 之后。"""

    group_id: str
    state: WorldState
    steps: tuple[ExecutedStep, ...] = ()
    candidate_action: GroundAction | None = None


@dataclass(frozen=True)
class SavedState:
    group_id: str
    order: int
    state: WorldState


def var(name: str, type_name: str) -> Term:
    return Term("var", name, type_name)


def const(value: str, type_name: str) -> Term:
    return Term("const", value, type_name)
