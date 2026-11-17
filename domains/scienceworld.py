"""ScienceWorld 恢复接口。move 不要求物体处于拿住状态。"""

from __future__ import annotations

from ..registry import Registry, flag_predicate
from ..structs import ActionStep, Atom, BindingSource, Failure, Rule, WorldState, make_entity, var
from ..trivalent import Tri


def _failure_says_closed(state: WorldState, args):
    related = [
        item
        for item in state.failures
        if item.tool == "move" and item.args == (args[0], args[1])
    ]
    if any(item.reason == "closed" for item in related):
        return Tri.TRUE
    if any(item.reason in {"unknown", "unparsed"} for item in related):
        return Tri.UNKNOWN
    return Tri.FALSE


def build_registry() -> Registry:
    registry = Registry("scienceworld")
    closed, closed_fields = flag_predicate("closed")
    registry.add_predicate("destinationClosed", ("destination",), closed, closed_fields)
    registry.add_predicate(
        "failureSaysClosed",
        ("object", "destination"),
        _failure_says_closed,
        lambda args: (f"fail:move:{args[0]}:{args[1]}",),
    )
    registry.add_verifier("v_opened", "opened")
    registry.add_template(
        "open",
        ("destination",),
        "opened",
        (0,),
        "v_opened",
        stage=(("destinationClosed", (0,)),),
    )
    registry.add_verifier("v_moved", "moved")
    registry.add_template(
        "move",
        ("object", "destination"),
        "moved",
        (0, 1),
        "v_moved",
    )
    return registry


def recovery_rule() -> Rule:
    obj = var("X", "object")
    dest = var("D", "destination")
    return Rule(
        (Atom("failureSaysClosed", (obj, dest)),),
        (
            BindingSource("X", "object", "action_arg", "move:0"),
            BindingSource("D", "destination", "action_arg", "move:1"),
        ),
        (ActionStep("open", (dest,)), ActionStep("move", (obj, dest))),
        ("v_opened", "v_moved"),
        "exec",
        "scienceworld",
        "moved",
        (obj, dest),
    )


def science_state(reason: str) -> WorldState:
    return WorldState(
        "scienceworld",
        (("description", "move the sample into the fridge"),),
        (
            make_entity("sample", "object"),
            make_entity("fridge", "destination", closed="true"),
        ),
        ("sample", "fridge"),
        (Failure("move", ("sample", "fridge"), reason),),
    )
