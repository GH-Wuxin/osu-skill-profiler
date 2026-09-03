# Active Learning v0.1 Dry-Run Evidence Report

Status: **PASS — INFRASTRUCTURE DRY RUN, NO HUMAN RESPONSES**

## UNAVAILABLE_CLASSIFICATION

```text
total:      42
legitimate: 41
unexpected:  1  (ALV01-UNAVAILABLE-001, contained)
unresolved:  0
gate:      PASS
```

Concrete reasons: 30 guarded Local slider-geometry segments, three Local
nonpositive-beat-length groups, three Reference geometry guards, two
single-object movement tails, two single-object Reference transitions, one
declared Feature duration aggregate absent, and one historical positive-only
Reference-summary defect.

## CANDIDATES

```text
total eligible: 33,796
MAP:             1,993
SEGMENT:        31,803

dense_timing_pressure_high:    999
movement_demand_high:          994
slider_tracking_travel_high: 31,803
```

The defect map is excluded. `slider_control_load_high` is excluded from this
dry run on human-judgeability grounds. Challenge membership contributes only
to audit sampling.

## BATCH

```text
tasks:            93
unique entities: 168
MAP/MAP:          21
SEGMENT/SEGMENT:  72

no-control:        73
exact repeat:       4
A/B inversion:      4
easy anchor:         4
ambiguous control:   4
within-map segment:  4
```

Selection reasons:

```text
boundary adjacent: 32
abstention heavy:  24
challenge audit:   17
easy anchor:        4
ambiguous control:  4
within-map segment: 4
exact repeat:       4
A/B inversion:      4
```

The 17 challenge-audit source pairs include legacy, pathological and/or
Reference-disagreement sampling membership. This metadata is absent from
blind presentation.

## DIVERSITY

```text
maps:    153
sets:    151
mappers: 141

maximum source-pair incidence per map:    3
maximum source-pair incidence per set:    3
maximum source-pair incidence per mapper: 4
```

Repeated and inverted tasks intentionally reuse source pairs and are excluded
from these ordinary-source concentration maxima.

## DETERMINISM AND SERIALIZATION

Seed:

```text
osu-skill-profiler-active-learning-v01
```

Canonical artifacts are strict UTF-8 JSON/JSONL with sorted object keys,
`allow_nan=false`, no non-finite values, timestamps, UUIDs or absolute paths.
Independent repeated generation is byte-identical.

```text
batch.jsonl
bytes: 194,934
sha256:f693f3018688b6acf64009988325cbdfdb86cc8829840367b44ef84b7bccb80b
```

The final manifest also records all input and output sizes/hashes. Generated
files are:

```text
batch.jsonl
blind_batch.jsonl
diagnostics.json
manifest.json
presentation_contract.json
unavailable_classification.jsonl
unavailable_summary.json
```

No real annotation campaign occurred. Therefore this report makes no claim
about player/map semantics, annotator agreement or taxonomy validity.
