# Frozen rule libraries

Nine exports, three domains × three runs (`ALF-LIB-01…03`, `SCI-LIB-01…03`,
`WEB-LIB-01…03`), plus the domain interfaces they were written against. Each
export is the library one run evaluated:

| Domain | Rules per export | Exec | Reject |
|---|---|---|---|
| ALFWorld | 47 | 39 | 8 |
| ScienceWorld | 52 | 42 | 10 |
| WebShop | 61 | 45 | 16 |

```python
from traj2rules.frozen import build_registry, load_library

registry = build_registry("alfworld")
meta, rules = load_library("ALF-LIB-01")
print(meta["run_id"], meta["training_library_seed"], len(rules))
print(rules[0].program)          # ActionStep(tool='open', ...), ActionStep(tool='move', ...)

# validate every export against the exported interface
# $ python -m traj2rules.frozen
```

## Layout

| Path | Content |
|---|---|
| `libraries/<LIB>.json` | One frozen library: `library_metadata`, `rules`, `field_provenance`, `notes` |
| `interfaces/<domain>.json` | Registered types, predicates, action templates (tool, parameter types, effect, verifier), rejection checkers |

Rule entries follow `output/supplementary_reference/templates/rule_library.template.json`:
`rule_id, tau, conditions, bindings, program, verifiers, canonical_form,
effect_signature, support_task_group_ids, counterexample_task_group_ids,
unknown_task_group_ids, selection_rank, selection_decision`.

## What is derived and what is reconstructed

`field_provenance` in each export states this per field group; the short version:

- **Derived from the reported listing:** `rule_id`, `tau`,
  `support_task_group_count`, `selection_rank`, `library_id`, `run_id`,
  `training_library_seed`. Counts, the exec/reject split and the ranking order
  match the per-rule usage table released with the submission.
- **Reconstructed against the interface:** `conditions`, `bindings`, `program`,
  `verifiers`, `canonical_form`, `effect_signature`. Every rule passes
  `traj2rules.rules.check_rule` (at most three start conditions, at most two
  execution steps or one checked rejection action, typed variables, inferable
  effect) and its canonical form round-trips through `parse_rule`.
- **Not recoverable:** `support_task_group_ids` and `unknown_task_group_ids`.
  Only the number of supporting task groups survives in the reported data, so
  these fields are `null`.
- **Anchored to the manuscript:** `ALF-EXEC-01`, `SCI-EXEC-04` and
  `WEB-REJECT-01` reproduce the three worked examples in Appendix A.3
  (predicate sequence, program, verifier sequence).

The exports are therefore a reconstruction that satisfies every constraint the
paper states, not a byte-level copy of the original training artefacts. Use them
to inspect, type-check and re-run rule selection; do not quote them as the
original model outputs.

## Interface scope

| Domain | Types | Predicates | Action templates | Rejection checkers |
|---|---|---|---|---|
| ALFWorld | object, receptacle | 12 | 7 | 3 |
| ScienceWorld | container, substance | 9 | 6 | 2 |
| WebShop | option, color, size | 10 | 4 | 2 |

`build_registry` returns a registry that can type-check rules. Predicate and
conflict-checker callables belong to the environment adapter and are not part of
this export, so the registry cannot evaluate a world state on its own.
