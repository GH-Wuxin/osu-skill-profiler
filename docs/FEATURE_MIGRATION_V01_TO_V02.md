# Feature Contract Migration: v0.1 to v0.2

Status: **IMPLEMENTED; pending independent re-verification**

| Contract | Version | Fields | Status |
| --- | ---: | ---: | --- |
| Historical Feature | `0.1.0` | 104 | frozen, replayable, contains documented errata |
| Corrected Feature | `0.2.0` | 106 | current default |

This migration repairs the Feature-layer consequences of red-team findings
RT-01 and RT-04. It does not rewrite Feature v0.1 or any historical artifact.

## Why a version bump was required

Feature v0.1 had two independent semantic problems:

1. slider duration and map end time used one-span duration even when a slider
   traversed multiple spans;
2. `slider.repeats_total` and `slider.repeats_max` summed the raw `.osu`
   `slides` field, which is a **span count**, while their names and contract
   claimed a **repeat count**.

Correcting either issue under `feature_version=0.1.0` would make historical
output unreplayable. The legacy extractor and schema therefore remain
available only through explicit `FeatureExtractor("0.1.0")` and
`FEATURE_SCHEMA_V01` selection.

## Canonical slider terminology

Feature v0.2 consumes the shared slider contract in
`src/osu_skill_profiler/slider_semantics.py`:

```text
span_count = max(1, parsed_slides)
repeat_count = span_count - 1
single_span_duration = path_distance / velocity
total_slider_duration = single_span_duration * span_count
end_time = start_time + total_slider_duration
```

The non-positive `slides` guard is retained and provenance remains explicit;
no silent clipping was introduced.

## Field migration

All unaffected v0.1 fields keep the same names and definitions. The two
ambiguous fields are removed from the v0.2 schema and replaced by four fields:

| Feature v0.1 | Historical value | Feature v0.2 replacement | Corrected value |
| --- | --- | --- | --- |
| `slider.repeats_total` | sum of span counts | `slider.repeat_count_total` | sum of `span_count - 1` |
| `slider.repeats_max` | maximum span count | `slider.repeat_count_max` | maximum `span_count - 1` |
| — | — | `slider.span_count_total` | sum of `.osu` span counts |
| — | — | `slider.span_count_max` | maximum `.osu` span count |

`slider.repeats_total` and `slider.repeats_max` are classified
`DEPRECATED_FOR_NEW_MODELS` by the executable leakage registry. They remain
valid only when replaying Feature v0.1.

## Duration changes

The existing `slider.duration_ms_*` family remains named the same in v0.2,
but now describes **total duration across all spans**. The following derived
values can change on maps with repeat sliders:

- `slider.duration_ms_*`;
- `temporal.map_duration_ms` when a repeat slider determines map end;
- `temporal.density_objects_per_s` when map duration changes;
- fixed-time segment boundaries and duration-derived aggregates whose end
  semantic depends on the corrected slider tail.

Non-repeat sliders have `span_count=1`, so the old and corrected duration are
identical for that class.

## Compatibility policy

- Old JSON with 104 fields remains valid only as Feature v0.1 historical
  evidence.
- New extraction defaults to Feature v0.2 and emits exactly 106 fields.
- Loaders must use the explicit version before interpreting repeat/span
  fields; field count alone is not a semantic version.
- Future model schemas may select corrected v0.2 observable candidates, but
  they may not select the two historical `slider.repeats_*` names.
- Historical `training/datasets/feature_qa/` artifacts are immutable.
  Corrected artifacts belong under `training/datasets/feature_qa_v02/`.

## Independent regression evidence

`tests/test_foundation_remediation_v01.py` contains hand-derived expectations
for zero/one/multiple repeats, odd/even parity, slider-to-circle and
slider-to-slider transitions, inherited timing/SV, old format, short/long
finite sliders and historical-bug mutations. The expected side does not call
the production slider helper.

The regression explicitly proves that:

- the historical one-span-duration mutation fails;
- substituting span count for repeat count fails;
- v0.1 remains replayable;
- v0.2 exposes unambiguous repeat and span fields.

Corpus-level corrected QA results and checksums are recorded in
`docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md`; they are not inferred from the
historical v0.1 PASS report.
