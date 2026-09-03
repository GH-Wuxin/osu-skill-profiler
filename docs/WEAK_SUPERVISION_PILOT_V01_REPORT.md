# Weak Supervision v0.1 Pilot Report

Status: **PASS — BOUNDED EVIDENCE PILOT, NOT LABEL DATASET**

Pre-campaign gates passed: 22 focused schema/oracle/pilot tests and an 8-map
real-data smoke producing 300 evidence records. The final expanded full suite
passes 226/226 tests.

## PILOT_SELECTION

```text
count: 1000 maps
generator_version: 0.1.0
seed: osu-skill-profiler-weak-supervision-pilot-v01
identity hash: sha256:5befe4cceff267eb7199367142dbe0f3abbea477fbcf7944dc3d06e3ed917c88
strategy: deterministic challenge quotas, then hash-ranked ordinary fill
```

Selection memberships (overlap is allowed, hence memberships exceed 1,000):

```text
ordinary: 775
legacy_format_ood: 124
pathological_challenge: 115
reference_disagreement_challenge: 28
```

Challenge/split membership was used only to select representation. It was not
passed to rule contexts, evidence values, or future model inputs.

## EVIDENCE

```text
total records: 35,854
EMITTED:       11,130
ABSTAINED:     24,682
UNAVAILABLE:      42
INVALID:            0

MAP:            4,000
SEGMENT:       31,854
```

By source family:

```text
OBSERVABLE:    3,000
LOCAL_SIGNAL: 31,854
REFERENCE_PPY: 1,000
```

By provisional proposition:

```text
dense_timing_pressure_high:  1,000
movement_demand_high:        2,000
slider_control_load_high:    1,000
slider_tracking_travel_high: 31,854
```

## COVERAGE

| Rule | Emission | Abstain | Unavailable | Invalid |
| --- | ---: | ---: | ---: | ---: |
| observable movement tail | 19.4% | 80.4% | 0.2% | 0% |
| ppy snap tail | 50.7% | 48.7% | 0.6% | 0% |
| dense timing | 45.0% | 55.0% | 0% | 0% |
| slider control load | 9.9% | 90.0% | 0.1% | 0% |
| Local slider-travel segment | 31.02% | 68.88% | 0.10% | 0% |

Unavailable patterns comprise 33 geometry-blocked Local segments, three
geometry-blocked Reference maps, three Reference-unavailable maps, and six
missing required signal cases. Abstention remains separate from zero-valued
negative evidence.

## DEPENDENCE

```text
correlated groups in real pilot: 0
entity/proposition groups with effective support 1: 10,748
entity/proposition groups with effective support 2:   191
independent agreement cases: 191
```

The two movement rules use disjoint declared roots and independence groups:
corrected observable movement tails versus Reference ppy snap policy. Tests
show two rule IDs with identical lineage collapse to one effective component.

## CONFLICT

```text
real-pilot directional disagreement cases: 0
real-pilot independent agreement cases: 191
```

This is a pilot observation, not evidence that sources universally agree.
The synthetic adversarial oracle creates independent positive/negative
evidence for the same entity/proposition and verifies it remains in
`strongest_disagreement`; no majority vote erases it.

## LEAKAGE

```text
independent observable input control: PASS
Reference overlap negative control:  FAIL as required
challenge metadata negative control: FAIL as required
```

The Reference control produces `FORBIDDEN_INPUT_ROLE` and
`TARGET_LINEAGE_LEAKAGE`. The challenge control produces
`FORBIDDEN_INPUT_ROLE`. Direct/transitive Reference lineage, unknown lineage,
split/challenge input, and valid-independent adversarial cases pass their
expected tests.

## SERIALIZATION

All outputs parse as strict UTF-8 JSON/JSONL with `allow_nan=false`. Nonfinite
count is zero. Record ordering is deterministic by stable identity. Output
validation rejects timestamps only by omission and rejects absolute Windows or
POSIX path-shaped strings mechanically.

| Artifact | Class | Bytes | SHA256 |
| --- | --- | ---: | --- |
| `selection.jsonl` | canonical | 120,860 | `5befe4cceff267eb7199367142dbe0f3abbea477fbcf7944dc3d06e3ed917c88` |
| `evidence.jsonl` | canonical | 37,364,440 | `be5d187af8510315943a686c5d43cc9be46a1b95d57ebaba96fef7816ec46a65` |
| `registries.json` | canonical | 11,377 | `60e41a0ecc24881ba0706d940c0e758c8668cf02b7d6ffa890766d21e73f1379` |
| `audit.json` | regenerable | 13,645 | `d68ea5cd8870450737d36bb5e7188dba79fa83e68bde2ef985c8414f5528ba98` |
| `leakage.json` | regenerable | 1,042 | `4656ec12f98518f3acd19a4d092e2158fb419a536fb751b55d0ffe508901614a` |

Pilot manifest SHA256:

```text
c5d1cc458a12b1919f40f64efa44c620a693031a623f97048ede067b03629469
```

Input artifact hashes are embedded in that manifest:

```text
Feature 0.2 5k:   27cd071e0589aecb45e9cf0e455e690aa07f3e6330667e8b6ac7aa4d1e09cdc7
Local 0.3 5k:     a51980fea5fcb4b0e4cb0b05234b7d746861f8ed72d478e3ef0f60c7db16dc1d
Reference 0.2 5k: 823b0c51952d402b3d937892524d17aad1f4091a92769401e2eb3a3ca4a92a6b
```

Estimated evidence size before the run was 38,500,000 bytes; actual size was
37,364,440 bytes. No full-corpus weak-evidence campaign was run.

## REPRODUCTION

With repository root as the working directory and `src` on `PYTHONPATH`:

```powershell
python tools/weak_supervision_pilot_v01.py --count 1000
```

The same generator version, seed, corrected 5k inputs, and environment must
reproduce the selection and artifact hashes above. Generated artifacts reside
under ignored local path `training/datasets/weak_supervision_v01/pilot/`.

## VERDICT

```text
WEAK_SUPERVISION_INFRASTRUCTURE: PASS
READY_FOR_ACTIVE_LEARNING_DESIGN: YES_WITH_CAVEATS
```

No taxonomy, final label, truth claim, model training, player inference, or
recommendation result follows from this pilot.
