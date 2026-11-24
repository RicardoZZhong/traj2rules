"""Load the frozen rule libraries shipped with the package.

Nine exports ship in ``libraries/`` (three domains x three runs). Each export
holds the rule library one run froze before its test-set evaluation: 47 rules for
ALFWorld, 52 for ScienceWorld and 61 for WebShop. Rule identifiers, types, build
support counts and in-library ranking match the frozen-library listing released
with the paper; the conditions, programs and verifiers of every rule are stored
alongside and pass :func:`traj2rules.rules.check_rule`.

The JSON payloads use the field layout of
``output/supplementary_reference/templates/rule_library.template.json``:
``rule_id, tau, conditions, bindings, program, verifiers, canonical_form,
effect_signature, support_task_group_count, counterexample_task_group_ids,
selection_rank, selection_decision``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from ..registry import Registry
from ..rules import check_rule, parse_rule, serialize
from ..structs import Rule

_ROOT = Path(__file__).resolve().parent
_INTERFACE_DIR = _ROOT / "interfaces"
_LIBRARY_DIR = _ROOT / "libraries"

DOMAINS = ("alfworld", "scienceworld", "webshop")
EXPECTED_RULE_COUNTS = {"alfworld": 47, "scienceworld": 52, "webshop": 61}
RUN_SEEDS = {"R1": 17, "R2": 43, "R3": 89}

ANCHORS = {
    "ALF-EXEC-01": (
        ["goal_requires_store", "cleaning_confirmed", "closed"],
        ["open", "move"],
        ["verify_opened", "verify_in"],
    ),
    "SCI-EXEC-04": (
        ["mixing_goal_active", "source_contains_required_paint", "mixing_container_identified"],
        ["pour_contents"],
        ["verify_transfer"],
    ),
    "WEB-REJECT-01": (
        ["is_color_option", "req_color", "opt_color"],
        ["click"],
        ["attribute_conflict"],
    ),
}

__all__ = [
    "ANCHORS",
    "DOMAINS",
    "EXPECTED_RULE_COUNTS",
    "RUN_SEEDS",
    "available_libraries",
    "build_registry",
    "interface_path",
    "iter_libraries",
    "library_ids",
    "library_path",
    "load_interface",
    "load_library",
    "metadata",
    "validate",
]


def library_path(library_id: str) -> Path:
    """Path of one shipped export."""
    return _LIBRARY_DIR / f"{library_id}.json"


def interface_path(domain: str) -> Path:
    """Path of one shipped domain interface."""
    return _INTERFACE_DIR / f"{domain}.json"


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_interface(domain: str) -> dict:
    """Return the interface payload for ``domain``."""
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}; expected one of {DOMAINS}")
    return _read_json(interface_path(domain))


def build_registry(domain: str) -> Registry:
    """Build a :class:`Registry` from a shipped domain interface.

    The interface carries the registered types, action templates, effects and
    verifier identifiers. Predicate and conflict-checker callables live in the
    environment adapter, so the returned registry type-checks rules and does not
    evaluate a world state on its own.
    """
    payload = load_interface(domain)
    registry = Registry(payload["domain"])
    for predicate in payload["predicates"]:
        registry.add_predicate(
            predicate["predicate_id"],
            tuple(predicate["argument_types"]),
            lambda state, args: None,
            lambda args: (),
        )
    for template in payload["templates"]:
        registry.add_template(
            template["tool_id"],
            tuple(template["parameter_types"]),
            template["effect_id"],
            tuple(template["effect_argument_index"]),
            template["verifier_id"],
        )
    for checker in payload["checkers"]:
        registry.add_checker(
            checker["checker_id"],
            checker["effect_id"],
            lambda state, binding, action: None,
            lambda binding: (),
        )
    return registry


def library_ids(domain: str | None = None) -> tuple[str, ...]:
    """Available library identifiers, optionally filtered by domain."""
    prefix = None
    if domain is not None:
        if domain not in DOMAINS:
            raise ValueError(f"unknown domain {domain!r}; expected one of {DOMAINS}")
        prefix = {"alfworld": "ALF", "scienceworld": "SCI", "webshop": "WEB"}[domain]
    ids = sorted(path.stem for path in _LIBRARY_DIR.glob("*.json"))
    if prefix is None:
        return tuple(ids)
    return tuple(item for item in ids if item.startswith(prefix + "-"))


def available_libraries() -> dict[str, tuple[str, ...]]:
    """Domain to library identifiers."""
    return {domain: library_ids(domain) for domain in DOMAINS}


def metadata(library_id: str) -> dict:
    """Return ``library_metadata`` and the free-form notes for one export."""
    payload = _read_json(library_path(library_id))
    return {**payload["library_metadata"], "notes": payload["notes"]}


def load_library(library_id: str) -> tuple[dict, list[Rule]]:
    """Return ``(metadata, rules)`` for one frozen library export."""
    payload = _read_json(library_path(library_id))
    meta = payload["library_metadata"]
    registry = build_registry(meta["domain"])
    rules: list[Rule] = []
    for entry in payload["rules"]:
        rule = parse_rule(entry["canonical_form"], registry)
        if rule is None:
            raise ValueError(f"{library_id}: rule {entry['rule_id']} does not type-check")
        rules.append(rule)
    return meta, rules


def iter_libraries(domain: str | None = None) -> Iterator[tuple[str, dict, list[Rule]]]:
    """Yield ``(library_id, metadata, rules)`` for every shipped export."""
    for library_id in library_ids(domain):
        meta, rules = load_library(library_id)
        yield library_id, meta, rules


def validate(library_id: str | None = None) -> list[str]:
    """Check every export; return a list of problems (empty when all pass)."""
    problems: list[str] = []
    targets = library_ids() if library_id is None else (library_id,)
    for target in targets:
        try:
            payload = _read_json(library_path(target))
        except FileNotFoundError:
            problems.append(f"{target}: export not found")
            continue
        meta = payload["library_metadata"]
        domain = meta["domain"]
        if domain not in DOMAINS:
            problems.append(f"{target}: unknown domain {domain!r}")
            continue
        expected = EXPECTED_RULE_COUNTS[domain]
        if meta["rule_count"] != expected or len(payload["rules"]) != expected:
            problems.append(f"{target}: {len(payload['rules'])} rules, expected {expected}")
        if RUN_SEEDS.get(meta["run_id"]) != meta["training_library_seed"]:
            problems.append(f"{target}: run {meta['run_id']} and seed {meta['training_library_seed']} disagree")
        registry = build_registry(domain)
        seen = set()
        for entry in payload["rules"]:
            rule_id = entry["rule_id"]
            if rule_id in seen:
                problems.append(f"{target}: duplicate rule_id {rule_id}")
            seen.add(rule_id)
            rule = parse_rule(entry["canonical_form"], registry)
            if rule is None:
                problems.append(f"{target}: {rule_id} does not parse against the interface")
                continue
            ok, reason = check_rule(rule, registry)
            if not ok:
                problems.append(f"{target}: {rule_id} fails check_rule ({reason})")
            if serialize(rule) != entry["canonical_form"]:
                problems.append(f"{target}: {rule_id} canonical form is not stable")
            if entry["support_task_group_count"] < 3:
                problems.append(f"{target}: {rule_id} support below n_min=3")
            if entry["counterexample_task_group_ids"]:
                problems.append(f"{target}: {rule_id} carries counterexamples")
            if rule_id in ANCHORS:
                predicates, tools, verifiers = ANCHORS[rule_id]
                if [atom.predicate for atom in rule.conditions] != predicates:
                    problems.append(f"{target}: {rule_id} condition sequence differs from the manuscript")
                if [step.tool for step in rule.program] != tools:
                    problems.append(f"{target}: {rule_id} program differs from the manuscript")
                if list(rule.verifiers) != verifiers:
                    problems.append(f"{target}: {rule_id} verifier sequence differs from the manuscript")
    return problems


def _main() -> int:
    problems = validate()
    counts = {domain: len(library_ids(domain)) for domain in DOMAINS}
    print("frozen libraries:", ", ".join(f"{domain}={counts[domain]}" for domain in DOMAINS))
    for library_id in library_ids():
        meta, rules = load_library(library_id)
        execs = sum(1 for rule in rules if rule.tau == "exec")
        print(f"  {library_id}: {len(rules)} rules ({execs} exec / {len(rules) - execs} reject), "
              f"run {meta['run_id']}, seed {meta['training_library_seed']}")
    if problems:
        print("\nproblems:")
        for item in problems:
            print(" -", item)
        return 1
    print("\nall exports pass check_rule and the appendix rules match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
