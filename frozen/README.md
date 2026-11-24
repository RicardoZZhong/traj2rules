# Frozen rule libraries

Nine exports, three domains × three runs (`ALF-LIB-01…03`, `SCI-LIB-01…03`,
`WEB-LIB-01…03`), together with the domain interfaces they were written against.
Each export is the library one run froze before its test-set evaluation:

| Domain | Rules per export | Exec | Reject |
|---|---|---|---|
| ALFWorld | 47 | 39 | 8 |
| ScienceWorld | 52 | 42 | 10 |
| WebShop | 61 | 45 | 16 |

Libraries `01`, `02`, `03` are the runs with seeds 17, 43 and 89.

```python
from traj2rules.frozen import build_registry, load_library

registry = build_registry("alfworld")
meta, rules = load_library("ALF-LIB-01")
print(meta["run_id"], meta["training_library_seed"], len(rules))
print(rules[0].program)          # ActionStep(tool='open', ...), ActionStep(tool='move', ...)
```

```sh
python -m traj2rules.frozen      # re-check every export
```

## Layout

| Path | Content |
|---|---|
| `libraries/<LIB>.json` | One frozen library: `library_metadata`, `rules`, `notes` |
| `interfaces/<domain>.json` | Registered types, predicates, action templates (tool, parameter types, effect, verifier), rejection checkers |

Rule entries follow `output/supplementary_reference/templates/rule_library.template.json`:
`rule_id, tau, conditions, bindings, program, verifiers, canonical_form,
effect_signature, support_task_group_count, counterexample_task_group_ids,
selection_rank, selection_decision`, plus a `display` block with the readable
form used in the paper (`goal_requires_store(X, D) & cleaning_confirmed(X) & closed(D)`).

## What the exports contain

- **Identifiers and counts.** `rule_id`, `tau`, `support_task_group_count`,
  `selection_rank`, `library_id`, `run_id` and `training_library_seed` match the
  frozen-library listing released with the paper: 47 / 52 / 61 rules per domain,
  split 39/8, 42/10 and 45/16 between execution and rejection rules, ranked by
  supporting task groups.
- **Rule content.** Conditions (at most three), programs (at most two execution
  steps, or one checked action for a rejection rule), bindings and verifiers,
  stored per rule and rendered in canonical form `C:…|I:…|K:…|V:…|tau:…`. Every
  rule passes `traj2rules.rules.check_rule`, and `canonical_form` round-trips
  through `parse_rule`.
- **Supporting task groups** are recorded as a count; the partition listing that
  carries group identifiers is released separately.
- **Appendix A.3 examples.** `ALF-EXEC-01`, `SCI-EXEC-04` and `WEB-REJECT-01` are
  the three rules quoted in the appendix; their predicate sequences, programs and
  verifier sequences match the manuscript.

## Interface scope

| Domain | Types | Predicates | Action templates | Rejection checkers |
|---|---|---|---|---|
| ALFWorld | object, receptacle | 12 | 7 | 3 |
| ScienceWorld | container, substance | 9 | 6 | 2 |
| WebShop | option, color, size | 10 | 4 | 2 |

`build_registry` returns a registry that type-checks rules and mirrors the
registered effects. Predicate and conflict-checker callables live in the
environment adapter, so the registry does not evaluate a world state on its own.

## Tests

`tests/test_frozen_libraries.py` checks the rule counts, the run/seed pairing,
`check_rule` and canonical-form stability for all 480 entries, the admission
threshold, and the three appendix rules.
