"""Frozen rule libraries and domain interfaces for the three evaluation domains.

Nine exports ship in ``libraries/`` (three domains x three runs). Each export
holds the rule library one run froze before its test-set evaluation: 47 rules for
ALFWorld, 52 for ScienceWorld and 61 for WebShop, with their conditions, programs
and verifiers. Rule identifiers, types, build support counts and in-library
ranking match the frozen-library listing released with the paper.

Typical use::

    from traj2rules.frozen import build_registry, load_library

    registry = build_registry("alfworld")
    meta, rules = load_library("ALF-LIB-01")
    rules[0].program          # (ActionStep(tool='open', ...), ActionStep(tool='move', ...))

Validate every export with ``python -m traj2rules.frozen``.
"""

from .loader import (
    ANCHORS,
    DOMAINS,
    EXPECTED_RULE_COUNTS,
    RUN_SEEDS,
    available_libraries,
    build_registry,
    interface_path,
    iter_libraries,
    library_ids,
    library_path,
    load_interface,
    load_library,
    metadata,
    validate,
)

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
