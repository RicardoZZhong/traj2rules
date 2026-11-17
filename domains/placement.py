"""放置接口。容器关闭时先打开，再移入已经拿住的物体。"""

from __future__ import annotations

from ..registry import Registry, flag_predicate
from ..structs import (
    ActionStep,
    Atom,
    BindingSource,
    Episode,
    ExecutedStep,
    Failure,
    Feedback,
    Rule,
    StepResult,
    WorldState,
    make_entity,
    var,
)


def build_registry(include_inspect: bool = False, include_alt_verifier: bool = False) -> Registry:
    registry = Registry("placement")
    for name in ("held", "closed", "open", "reachable"):
        evaluate, fields = flag_predicate(name)
        registry.add_predicate(name, ("object",) if name == "held" else ("container",), evaluate, fields)
    registry.add_predicate(
        "lastFailClosed",
        ("object", "container"),
        _last_fail_closed,
        lambda args: (f"fail:move:{args[0]}:{args[1]}",),
    )
    registry.add_verifier("v_open", "open")
    if include_alt_verifier:
        registry.add_verifier("v_open_alt", "open")
    allowed = ("v_open", "v_open_alt") if include_alt_verifier else ("v_open",)
    registry.add_template(
        "open",
        ("container",),
        "open",
        (0,),
        "v_open",
        stage=(("reachable", (0,)), ("closed", (0,))),
        allowed_verifiers=allowed,
    )
    registry.add_verifier("v_in", "in")
    registry.add_template(
        "move",
        ("object", "container"),
        "in",
        (0, 1),
        "v_in",
        stage=(("held", (0,)), ("open", (1,))),
    )
    if include_inspect:
        evaluate, fields = flag_predicate("needs_inspect")
        registry.add_predicate("needsInspect", ("container",), evaluate, fields)
        registry.add_verifier("v_inspect", "inspected")
        registry.add_template(
            "inspect",
            ("container",),
            "inspected",
            (0,),
            "v_inspect",
            stage=(("needsInspect", (0,)),),
        )
    return registry


def _last_fail_closed(state: WorldState, args):
    from ..trivalent import Tri

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


def in_effect() -> tuple:
    return ("placement", "exec", "in", (("var", "object"), ("var", "container")))


def make_recovery_rule(include_held: bool, open_verifier: str = "v_open") -> Rule:
    obj = var("X", "object")
    dest = var("D", "container")
    conditions = [
        Atom("lastFailClosed", (obj, dest)),
        Atom("closed", (dest,)),
    ]
    if include_held:
        conditions.append(Atom("held", (obj,)))
    return Rule(
        tuple(conditions),
        (
            BindingSource("X", "object", "action_arg", "move:0"),
            BindingSource("D", "container", "action_arg", "move:1"),
        ),
        (
            ActionStep("open", (dest,)),
            ActionStep("move", (obj, dest)),
        ),
        (open_verifier, "v_in"),
        "exec",
        "placement",
        "in",
        (obj, dest),
    )


def make_inspect_rule() -> Rule:
    dest = var("D", "container")
    return Rule(
        (Atom("needsInspect", (dest,)),),
        (BindingSource("D", "container", "visible", "container"),),
        (ActionStep("inspect", (dest,)),),
        ("v_inspect",),
        "exec",
        "placement",
        "inspected",
        (dest,),
    )


def placement_state(held: str = "true", failure_reason: str = "closed", mark: str | None = None) -> WorldState:
    goal = [("description", "place thermometer in freezer")]
    if mark is not None:
        goal.append(("mark", mark))
    return WorldState(
        "placement",
        tuple(goal),
        (
            make_entity("thermometer", "object", held=held),
            make_entity(
                "freezer",
                "container",
                closed="true",
                open="false",
                reachable="true",
                needs_inspect="false",
            ),
        ),
        ("thermometer", "freezer"),
        (Failure("move", ("thermometer", "freezer"), failure_reason),),
    )


def _episode(group_id: str, held: str, move_status: str) -> Episode:
    registry = build_registry()
    state = placement_state(held=held)
    open_action = registry.make_action("open", ("freezer",))
    move_action = registry.make_action("move", ("thermometer", "freezer"))
    move_feedback = (
        Feedback("confirm", "in", ("thermometer", "freezer"), "placed")
        if move_status == "confirm"
        else Feedback("reject", None, (), "not held")
    )
    return Episode(
        group_id,
        state,
        (
            ExecutedStep(open_action, Feedback("confirm", "open", ("freezer",), "opened")),
            ExecutedStep(move_action, move_feedback),
        ),
    )


def sample_episodes() -> list[Episode]:
    return [
        _episode("s1", "true", "confirm"),
        _episode("s2", "true", "confirm"),
        _episode("s3", "true", "confirm"),
        _episode("bad", "false", "reject"),
    ]


class PlacementEnv:
    def __init__(self, held: bool | None = True, needs_inspect: bool = False):
        self.held = held
        self.closed = True
        self.open = False
        self.reachable = True
        self.needs_inspect = needs_inspect
        self.failures = [Failure("move", ("thermometer", "freezer"), "closed")]
        self.fail_open_once = False
        self.unknown_but_apply = False
        self.drop_held_after_open = False

    def snapshot(self) -> WorldState:
        if self.held is None:
            thermometer = make_entity("thermometer", "object")
        else:
            thermometer = make_entity(
                "thermometer", "object", held="true" if self.held else "false"
            )
        freezer = make_entity(
            "freezer",
            "container",
            closed="true" if self.closed else "false",
            open="true" if self.open else "false",
            reachable="true" if self.reachable else "false",
            needs_inspect="true" if self.needs_inspect else "false",
        )
        return WorldState(
            "placement",
            (("description", "place thermometer in freezer"),),
            (thermometer, freezer),
            ("thermometer", "freezer"),
            tuple(self.failures),
        )

    def reset(self) -> WorldState:
        return self.snapshot()

    def step(self, action) -> StepResult:
        if action.tool == "open" and action.args == ("freezer",):
            return self._open()
        if action.tool == "inspect" and action.args == ("freezer",):
            feedback = Feedback("confirm", "inspected", ("freezer",), "inspected")
            return StepResult(self.snapshot(), feedback, False, False, None)
        if action.tool == "move" and action.args == ("thermometer", "freezer"):
            return self._move()
        feedback = Feedback("reject", None, (), "unsupported")
        return StepResult(self.snapshot(), feedback, False, False, None)

    def _open(self) -> StepResult:
        if self.fail_open_once:
            self.fail_open_once = False
            feedback = Feedback("unknown", None, (), "feedback missing")
            return StepResult(self.snapshot(), feedback, False, False, None)
        if self.reachable and self.closed:
            self.closed = False
            self.open = True
            if self.drop_held_after_open:
                self.held = None
            if self.unknown_but_apply:
                self.unknown_but_apply = False
                feedback = Feedback("unknown", None, (), "unparsed feedback")
                return StepResult(self.snapshot(), feedback, False, False, None)
            feedback = Feedback("confirm", "open", ("freezer",), "opened")
            return StepResult(self.snapshot(), feedback, False, False, None)
        feedback = Feedback("reject", None, (), "cannot open")
        return StepResult(self.snapshot(), feedback, False, False, None)

    def _move(self) -> StepResult:
        if not self.held:
            self.failures = [Failure("move", ("thermometer", "freezer"), "not_held")]
            feedback = Feedback("reject", None, (), "not held")
            return StepResult(self.snapshot(), feedback, False, False, None)
        if not self.open:
            self.failures = [Failure("move", ("thermometer", "freezer"), "closed")]
            feedback = Feedback("reject", None, (), "container closed")
            return StepResult(self.snapshot(), feedback, False, False, None)
        feedback = Feedback("confirm", "in", ("thermometer", "freezer"), "placed")
        return StepResult(self.snapshot(), feedback, True, True, 1.0)
