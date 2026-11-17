"""WebShop 的数量冲突接口：只比较同一属性，并做单位换算。"""

from __future__ import annotations

from ..registry import Registry
from ..structs import (
    ActionStep,
    Atom,
    BindingSource,
    Episode,
    Feedback,
    Rule,
    StepResult,
    WorldState,
    make_entity,
    var,
)
from ..trivalent import Tri

_WORDS = {"one": 1, "two": 2, "three": 3, "six": 6, "twelve": 12}


def parse_quantity(text: str) -> float | None:
    raw = " ".join(str(text).strip().lower().replace("_", "-").split())
    if raw == "":
        return None
    if raw.endswith("-pack"):
        head = raw[: -len("-pack")]
        if head in _WORDS:
            return float(_WORDS[head])
        try:
            return float(head)
        except ValueError:
            return None
    parts = raw.split(" ")
    if len(parts) == 2 and parts[1] in {"dozen", "pack", "packs"}:
        try:
            number = float(parts[0])
        except ValueError:
            return None
        factor = 12.0 if parts[1] == "dozen" else 1.0
        return number * factor
    try:
        return float(raw)
    except ValueError:
        return None


def _quantities(state: WorldState, option_id: str):
    goal = parse_quantity(state.goal_dict().get("quantity", ""))
    entity = state.entity(option_id)
    option = None if entity is None else parse_quantity(entity.get("quantity"))
    return goal, option


def _mismatch(state: WorldState, args):
    goal, option = _quantities(state, args[0])
    if goal is None or option is None:
        return Tri.UNKNOWN
    return Tri.FALSE if abs(goal - option) < 1e-9 else Tri.TRUE


def _visible(state: WorldState, args):
    entity = state.entity(args[0])
    if entity is None or entity.get("quantity") == "":
        return Tri.UNKNOWN
    return Tri.TRUE if parse_quantity(entity.get("quantity")) is not None else Tri.UNKNOWN


def _fields(args):
    return (f"entity:{args[0]}:quantity", "goal:quantity")


def _conflict(state: WorldState, _binding, action):
    if not action.args:
        return Tri.UNKNOWN
    return _mismatch(state, action.args)


def build_registry() -> Registry:
    registry = Registry("webshop")
    registry.add_predicate("quantityVisible", ("option",), _visible, _fields)
    registry.add_predicate("quantityMismatch", ("option",), _mismatch, _fields)
    registry.add_verifier("v_buy", "purchased")
    registry.add_template("buy", ("option",), "purchased", (0,), "v_buy")
    registry.add_checker("quantity_conflict", "conflict", _conflict, lambda _binding: ("goal:quantity",))
    return registry


def mismatch_rule() -> Rule:
    option = var("O", "option")
    return Rule(
        (Atom("quantityMismatch", (option,)),),
        (BindingSource("O", "option", "examined", "0"),),
        (ActionStep("buy", (option,)),),
        ("quantity_conflict",),
        "reject",
        "webshop",
        "conflict",
        (option,),
    )


def visible_rule() -> Rule:
    option = var("O", "option")
    return Rule(
        (Atom("quantityVisible", (option,)),),
        (BindingSource("O", "option", "examined", "0"),),
        (ActionStep("buy", (option,)),),
        ("quantity_conflict",),
        "reject",
        "webshop",
        "conflict",
        (option,),
    )


def option_state(quantity: str | None, goal: str = "6") -> WorldState:
    attrs = {} if quantity is None else {"quantity": quantity}
    return WorldState(
        "webshop",
        (("quantity", goal),),
        (make_entity("opt", "option", **attrs),),
        ("opt",),
    )


def option_episode(group_id: str, quantity: str | None, registry: Registry | None = None) -> Episode:
    registry = registry or build_registry()
    state = option_state(quantity)
    action = registry.make_action("buy", ("opt",))
    return Episode(group_id, state, candidate_action=action)


def sample_episodes(registry: Registry | None = None) -> list[Episode]:
    registry = registry or build_registry()
    return [
        option_episode("p1", "twelve-pack", registry),
        option_episode("p2", "12", registry),
        option_episode("p3", "1 dozen", registry),
        option_episode("bad", "6", registry),
    ]


def purchase_matches(goal: dict, entity) -> bool:
    """最终购买对照目标中的全部属性。拒绝规则只检查自己注册的那一项。"""
    if entity is None:
        return False
    checked = False
    if "quantity" in goal:
        checked = True
        required = parse_quantity(goal["quantity"])
        observed = parse_quantity(entity.get("quantity"))
        if required is None or observed is None or abs(required - observed) >= 1e-9:
            return False
    for key, required in goal.items():
        if key in {"quantity", "description"}:
            continue
        checked = True
        observed = entity.get(key, "")
        if observed == "" or observed.lower() != str(required).lower():
            return False
    return checked


def _option_attrs(spec) -> dict:
    if spec is None:
        return {}
    if isinstance(spec, str):
        return {"quantity": spec}
    return {str(key): str(value) for key, value in spec.items()}


class WebShopEnv:
    def __init__(self, quantities=("twelve-pack", "6"), goal=(("quantity", "6"),)):
        self.quantities = tuple(quantities)
        self.goal = tuple(goal)
        self.purchased = None

    def snapshot(self) -> WorldState:
        entities = []
        visible = []
        for index, spec in enumerate(self.quantities):
            entity_id = f"opt{index}"
            entities.append(make_entity(entity_id, "option", **_option_attrs(spec)))
            visible.append(entity_id)
        return WorldState("webshop", self.goal, tuple(entities), tuple(visible))

    def reset(self) -> WorldState:
        return self.snapshot()

    def step(self, action) -> StepResult:
        self.purchased = action.args[0] if action.args else None
        state = self.snapshot()
        entity = state.entity(self.purchased) if self.purchased else None
        success = purchase_matches(dict(self.goal), entity)
        feedback = Feedback(
            "confirm" if success else "reject",
            "purchased" if success else None,
            action.args,
        )
        return StepResult(state, feedback, True, success, 1.0 if success else 0.0)
