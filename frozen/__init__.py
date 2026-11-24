"""Frozen rule libraries and domain interfaces for the three evaluation domains.

Nine exports are shipped (three domains x three runs). Each export holds the
frozen rule library that one run evaluated: 47 rules for ALFWorld, 52 for
ScienceWorld and 61 for WebShop. Rule identifiers, rule types, build support
counts and in-library ranking come from the reported frozen-library listing;
the conditional/program content was reconstructed against the exported domain
interfaces and validated with :func:`traj2rules.rules.check_rule`.

Typical use::

    from traj2rules.frozen import load_library, build_registry

    registry = build_registry("alfworld")
    meta, rules = load_library("ALF-LIB-01")
    rules[0].program          # (ActionStep(tool='open', ...), ActionStep(tool='move', ...))

Run ``python -m traj2rules.frozen`` to validate every export.
"""

from .loader import (
    DOMAINS,
    EXPECTED_RULE_COUNTS,
    RUN_SEEDS,
    available_libraries,
    build_registry,
    iter_libraries,
    library_ids,
    load_interface,
    load_library,
    metadata,
    validate,
)

__all__ = [
    "DOMAINS",
    "EXPECTED_RULE_COUNTS",
    "RUN_SEEDS",
    "available_libraries",
    "build_registry",
    "iter_libraries",
    "library_ids",
    "load_interface",
    "load_library",
    "metadata",
    "validate",
]
