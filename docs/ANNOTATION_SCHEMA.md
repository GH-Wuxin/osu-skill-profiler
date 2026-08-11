# Future Human Annotation Contracts

This phase deliberately does **not** build an annotation website or collect
human labels. It defines the data contracts so that future annotation work can
start without redesigning the pipeline.

Machine-readable schemas: `src/osu_skill_profiler/schema/annotation_schema.py`.
Validation uses the stdlib-only validator in
`src/osu_skill_profiler/schema/validate.py`.

## Absolute / ordinal annotation

```json
{
  "annotation_id": "ann-001",
  "skill": "jump_aim",
  "annotator_id": "annotator-7",
  "beatmap_id": 123456,
  "beatmapset_id": 123,
  "mapper": "mapper-name",
  "reference": "path/to/map.osu",
  "value": "high"
}
```

Allowed values: `none`, `low`, `medium`, `high`, `dominant`.

## Pairwise comparison

```json
{
  "annotation_id": "ann-002",
  "skill": "stream",
  "annotator_id": "annotator-7",
  "a_ref": "map-a.osu",
  "b_ref": "map-b.osu",
  "value": "a_higher"
}
```

Allowed values: `a_much_higher`, `a_higher`, `similar`, `b_higher`,
`b_much_higher`.

## Segment annotation

```json
{
  "annotation_id": "ann-003",
  "skill": "rhythm_complexity",
  "annotator_id": "annotator-7",
  "segment_index": 3,
  "segment_range": { "start_ms": 15000, "end_ms": 20000 },
  "value": "medium"
}
```

`segment_index` and `segment_range` are optional; at least one should be used
to locate the segment.

## Annotator metadata & reliability

```json
{
  "annotator_id": "annotator-7",
  "reliability": 0.82,
  "notes": "prefers 4K-style commentary"
}
```

`reliability` must be in `[0, 1]`.

## Blind repeated judgment

```json
{
  "repeat_group": "pair-018",
  "session_id": "session-2026-01",
  "judgment_id": "judgment-3"
}
```

This supports repeated, blind judgments of the same item so annotator
self-consistency can be measured.

## What the schemas enforce

- Every annotation needs an `annotation_id`, a `skill`, and an `annotator_id`.
- Absolute/segment values use the fixed ordinal enum.
- Pairwise values use the fixed pairwise enum.
- Annotator reliability is bounded.
- All validation is deterministic and dependency-free.
