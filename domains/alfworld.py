"""ALFWorld 接口：处理状态不可观察时，规则不自动执行放置。"""

from __future__ import annotations

from ..registry import Registry
from ..structs import ActionStep, Atom, BindingSource, Rule, WorldState, make_entity, var
from ..trivalent import Tri


def _treatment(state: WorldState, args):
    required = state.goal_dict().get("treatment", "")
    if required == "":
        return Tri.TRUE
    entity = state.entity(args[0])
    if entity is None or entity.get("treatment") == "":
        return Tri.UNKNOWN
    return Tri.TRUE if entity.get("treatment") == required else Tri.FALSE


def build_registry() -> Registry:
    registry = Registry("alfworld")
    registry.add_predicate(
        "treatmentSatisfied",
        ("object",),
        _treatment,
        lambda args: (f"entity:{args[0]}:treatment", "goal:treatment"),
    )
    registry.add_verifier("v_placed", "placed")
    registry.add_template("place", ("object", "receptacle"), "placed", (0, 1), "v_placed")
    return registry


def place_rule() -> Rule:
    obj = var("X", "object")
    dest = var("D", "receptacle")
    return Rule(
        (Atom("treatmentSatisfied", (obj,)),),
        (
            BindingSource("X", "object", "visible", "object"),
            BindingSource("D", "receptacle", "visible", "receptacle"),
        ),
        (ActionStep("place", (obj, dest)),),
        ("v_placed",),
        "exec",
        "alfworld",
        "placed",
        (obj, dest),
    )


def alf_state(treatment: str | None) -> WorldState:
    attrs = {} if treatment is None else {"treatment": treatment}
    return WorldState(
        "alfworld",
        (("treatment", "clean"), ("description", "clean then place"),),
        (
            make_entity("apple", "object", **attrs),
            make_entity("fridge", "receptacle"),
        ),
        ("apple", "fridge"),
    )
