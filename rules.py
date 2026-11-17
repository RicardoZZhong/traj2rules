"""规则的类型检查、文本规范和解析。

条件按注册表顺序排列，变量在类型约束下重命名。
规范文本的字段顺序是条件、动作模板、绑定来源、校验器、规则类型。
"""

from __future__ import annotations

from collections import defaultdict
from itertools import product, permutations

from .registry import Registry
from .structs import ActionStep, Atom, BindingSource, Rule, Term


def serialize_term(term: Term) -> str:
    mark = "?" if term.kind == "var" else "="
    return f"{mark}{term.value}:{term.type_name}"


def serialize_atom(atom: Atom) -> str:
    args = ",".join(serialize_term(term) for term in atom.args)
    return f"{atom.predicate}({args})"


def serialize_step(step: ActionStep) -> str:
    args = ",".join(serialize_term(term) for term in step.args)
    return f"{step.tool}({args})"


def serialize_binding(source: BindingSource) -> str:
    term = Term("var", source.variable, source.type_name)
    return f"{serialize_term(term)}@{source.origin}:{source.detail}"


def serialize(rule: Rule) -> str:
    conditions = "&".join(serialize_atom(atom) for atom in rule.conditions)
    program = ";".join(serialize_step(step) for step in rule.program)
    bindings = ";".join(serialize_binding(source) for source in rule.bindings)
    verifiers = ";".join(rule.verifiers)
    return f"C:{conditions}|I:{program}|K:{bindings}|V:{verifiers}|tau:{rule.tau}"


def check_rule(rule: Rule, registry: Registry) -> tuple[bool, str]:
    if rule.domain != registry.domain:
        return False, "domain"
    if rule.tau not in {"exec", "reject"}:
        return False, "tau"
    if not registry.min_conditions <= len(rule.conditions) <= registry.max_conditions:
        return False, "condition_count"
    limit = 1 if rule.tau == "reject" else registry.max_program_length
    if not 1 <= len(rule.program) <= limit:
        return False, "program_length"
    usage: dict[str, str] = {}

    def use(term: Term, expected: str) -> bool:
        if term.type_name != expected:
            return False
        if term.kind == "var":
            previous = usage.get(term.value)
            if previous is not None and previous != term.type_name:
                return False
            usage[term.value] = term.type_name
        return True

    for atom in rule.conditions:
        predicate = registry.predicates.get(atom.predicate)
        if predicate is None or len(atom.args) != len(predicate.arg_types):
            return False, "predicate"
        for term, expected in zip(atom.args, predicate.arg_types):
            if not use(term, expected):
                return False, "predicate_type"
    for step in rule.program:
        template = registry.templates.get(step.tool)
        if template is None or len(step.args) != len(template.param_types):
            return False, "template"
        for term, expected in zip(step.args, template.param_types):
            if not use(term, expected):
                return False, "template_type"
    if len({source.variable for source in rule.bindings}) != len(rule.bindings):
        return False, "duplicate_binding"
    for source in rule.bindings:
        if usage.get(source.variable) != source.type_name:
            return False, "binding_type"
        if source.origin not in {"action_arg", "visible", "literal", "examined"}:
            return False, "origin"
        if not _binding_detail_ok(source, rule, registry):
            return False, "binding_detail"
    if set(usage) != {source.variable for source in rule.bindings}:
        return False, "binding_coverage"
    effect_id, effect_args = infer_effect(rule, registry)
    if effect_id is None or rule.effect_id != effect_id or rule.effect_args != effect_args:
        return False, "effect"
    if rule.tau == "exec":
        if len(rule.verifiers) != len(rule.program):
            return False, "verifiers"
        for step, verifier_id in zip(rule.program, rule.verifiers):
            template = registry.templates[step.tool]
            verifier = registry.verifiers.get(verifier_id)
            if verifier is None or verifier_id not in template.allowed_verifiers:
                return False, "verifier"
            if verifier.effect_id != template.effect_id:
                return False, "verifier_effect"
    else:
        if len(rule.verifiers) != 1 or rule.verifiers[0] not in registry.checkers:
            return False, "checker"
    return True, ""


def typecheck(rule: Rule, registry: Registry) -> bool:
    return check_rule(rule, registry)[0]


def _binding_detail_ok(source: BindingSource, rule: Rule, registry: Registry) -> bool:
    try:
        if source.origin == "action_arg":
            tool, index_text = source.detail.split(":", 1)
            template = registry.templates.get(tool)
            index = int(index_text)
            return (
                template is not None
                and 0 <= index < len(template.param_types)
                and template.param_types[index] == source.type_name
            )
        if source.origin == "examined":
            index = int(source.detail)
            step = rule.program[0]
            return (
                0 <= index < len(step.args)
                and step.args[index].kind == "var"
                and step.args[index].value == source.variable
            )
        if source.origin == "literal":
            return source.detail != ""
        return True
    except ValueError:
        return False


def infer_effect(rule: Rule, registry: Registry):
    if rule.tau == "exec":
        if not rule.program:
            return None, None
        step = rule.program[-1]
        template = registry.templates.get(step.tool)
        if template is None or any(index >= len(step.args) for index in template.effect_arg_index):
            return None, None
        args = tuple(step.args[index] for index in template.effect_arg_index)
        return template.effect_id, args
    if not rule.program or not rule.verifiers:
        return None, None
    checker = registry.checkers.get(rule.verifiers[0])
    if checker is None:
        return None, None
    return checker.effect_id, rule.program[0].args


def effect_key(rule: Rule) -> tuple:
    args = []
    for term in rule.effect_args:
        if term.kind == "const":
            args.append(("const", term.type_name, term.value))
        else:
            args.append(("var", term.type_name))
    return (rule.domain, rule.tau, rule.effect_id, tuple(args))


def canonicalize(rule: Rule, registry: Registry) -> tuple[Rule, str]:
    ok, reason = check_rule(rule, registry)
    if not ok:
        raise ValueError(reason)
    best_rule = None
    best_text = None
    for mapping in _renamings(rule):
        renamed = _apply_mapping(rule, mapping)
        ordered = _order_rule(renamed, registry)
        text = serialize(ordered)
        if best_text is None or text < best_text:
            best_text = text
            best_rule = ordered
    return best_rule, best_text


def _renamings(rule: Rule):
    groups = defaultdict(list)
    seen = set()

    def add(name: str, type_name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        groups[type_name].append(name)

    for atom in rule.conditions:
        for term in atom.args:
            if term.kind == "var":
                add(term.value, term.type_name)
    for step in rule.program:
        for term in step.args:
            if term.kind == "var":
                add(term.value, term.type_name)
    for source in rule.bindings:
        add(source.variable, source.type_name)
    for term in rule.effect_args:
        if term.kind == "var":
            add(term.value, term.type_name)
    types = sorted(groups)
    if not types:
        yield {}
        return
    pools = [list(permutations(groups[type_name])) for type_name in types]
    for choice in product(*pools):
        mapping = {}
        for type_name, perm in zip(types, choice):
            for index, old in enumerate(perm):
                mapping[old] = f"{type_name}{index}"
        yield mapping


def _rename_term(term: Term, mapping: dict[str, str]) -> Term:
    if term.kind == "const":
        return term
    return Term("var", mapping[term.value], term.type_name)


def _apply_mapping(rule: Rule, mapping: dict[str, str]) -> Rule:
    conditions = tuple(
        Atom(atom.predicate, tuple(_rename_term(term, mapping) for term in atom.args))
        for atom in rule.conditions
    )
    program = tuple(
        ActionStep(step.tool, tuple(_rename_term(term, mapping) for term in step.args))
        for step in rule.program
    )
    bindings = tuple(
        BindingSource(
            mapping[source.variable], source.type_name, source.origin, source.detail
        )
        for source in rule.bindings
    )
    effect_args = tuple(_rename_term(term, mapping) for term in rule.effect_args)
    return Rule(
        conditions,
        bindings,
        program,
        rule.verifiers,
        rule.tau,
        rule.domain,
        rule.effect_id,
        effect_args,
    )


def _order_rule(rule: Rule, registry: Registry) -> Rule:
    conditions = tuple(
        sorted(
            rule.conditions,
            key=lambda atom: (
                registry.predicates[atom.predicate].order,
                tuple(serialize_term(term) for term in atom.args),
            ),
        )
    )
    bindings = tuple(
        sorted(rule.bindings, key=lambda source: (source.variable, source.origin, source.detail))
    )
    return Rule(
        conditions,
        bindings,
        rule.program,
        rule.verifiers,
        rule.tau,
        rule.domain,
        rule.effect_id,
        rule.effect_args,
    )


def parse_rule(text: str, registry: Registry) -> Rule | None:
    try:
        parsed = _parse(text, registry)
    except (ValueError, KeyError, IndexError):
        return None
    if not typecheck(parsed, registry):
        return None
    rule, _ = canonicalize(parsed, registry)
    return rule


def _parse(text: str, registry: Registry) -> Rule:
    fields = {}
    for part in text.split("|"):
        key, value = part.split(":", 1)
        fields[key] = value
    conditions = tuple(
        _parse_atom(piece) for piece in fields["C"].split("&") if piece
    )
    program = tuple(_parse_step(piece) for piece in fields["I"].split(";") if piece)
    bindings = tuple(
        _parse_binding(piece) for piece in fields["K"].split(";") if piece
    )
    verifiers = tuple(piece for piece in fields["V"].split(";") if piece)
    tau = fields["tau"]
    provisional = Rule(conditions, bindings, program, verifiers, tau, registry.domain, "", ())
    effect_id, effect_args = infer_effect(provisional, registry)
    if effect_id is None:
        raise ValueError("effect")
    return Rule(
        conditions,
        bindings,
        program,
        verifiers,
        tau,
        registry.domain,
        effect_id,
        effect_args,
    )


def _parse_term(text: str) -> Term:
    mark, body = text[0], text[1:]
    if mark not in "?=":
        raise ValueError(text)
    value, type_name = body.split(":", 1)
    kind = "var" if mark == "?" else "const"
    return Term(kind, value, type_name)


def _parse_atom(text: str) -> Atom:
    name, rest = text.split("(", 1)
    if not rest.endswith(")"):
        raise ValueError(text)
    inner = rest[:-1]
    args = () if inner == "" else tuple(_parse_term(piece) for piece in inner.split(","))
    return Atom(name, args)


def _parse_step(text: str) -> ActionStep:
    atom = _parse_atom(text)
    return ActionStep(atom.predicate, atom.args)


def _parse_binding(text: str) -> BindingSource:
    term_text, rest = text.split("@", 1)
    origin, detail = rest.split(":", 1)
    term = _parse_term(term_text)
    if term.kind != "var":
        raise ValueError(text)
    return BindingSource(term.value, term.type_name, origin, detail)
