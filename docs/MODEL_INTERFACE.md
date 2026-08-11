# Model Interface

## Contract

```python
class SkillProfiler(Protocol):
    model_version: str
    taxonomy_version: str

    def analyze_map(self, source) -> dict: ...
    def analyze_segments(self, source) -> list[dict]: ...
```

Consumers call `analyze_map` and receive a versioned JSON document; they never
need to know whether the backend is a heuristic, LightGBM, XGBoost, a neural
network, or ONNX.

Current implementation: `DeterministicBaselineProfiler`
(`src/osu_skill_profiler/models/baseline.py`).

## Output schema

```json
{
  "schema_version": "0.1.0",
  "taxonomy_version": "v0.0.1",
  "model_version": "deterministic-baseline-0.1.0",
  "model_kind": "baseline",
  "status": "not_inferred",
  "disclaimer": "BASELINE / NOT TRAINED / NOT GROUND TRUTH",
  "beatmap": {
    "beatmap_id": 1000001,
    "beatmapset_id": 2000001,
    "mapper": "fixture-mapper",
    "difficulty_name": "Normal",
    "source": "path/to/map.osu",
    "difficulty": {
      "AR": 9.0,
      "OD": 8.0,
      "CS": 4.0,
      "HP": 5.0,
      "SliderMultiplier": 1.8,
      "SliderTickRate": 1.0
    }
  },
  "features": {},
  "skills": {
    "jump_aim": { "score": null, "confidence": null, "status": "not_inferred" }
  },
  "segments": [],
  "weak_labels": []
}
```

Semantics:

- `status: "not_inferred"` means no model produced a score. `score` and
  `confidence` must be `null` in that state.
- `status: "weak_candidate"` (future) means the value came from weak
  supervision only, never from a human label.
- `status: "inferred"` (future) means a trained model produced the value.
- The vectorized features are the primary data contract; primary/secondary
  skill labels are only ever derived convenience outputs.

## Weak labels

Weak-label records carry `rule_id`, `skill`, `suggested_score`, `confidence`,
`evidence`, `segment_index`, `features_version`, `taxonomy_version`,
`input_checksum`, and the disclaimer `WEAK LABEL != GROUND TRUTH`.

They are candidate signals, never ground truth, and must not be consumed as
labels.

## Evaluation contract

`src/osu_skill_profiler/evaluation/metrics.py` provides pure,
dependency-free metrics for the future evaluation pipeline:

- regression: `mae`, `rmse`, `pearson_r`
- ranking: `kendall_tau`
- classification: `accuracy`, `balanced_accuracy`, `macro_f1`

These are contracts, not results. The project currently makes no accuracy
claim because it has no trained model and no ground-truth labels.

## Roadmap for backends

1. **Heuristic baseline** (current): deterministic, `not_inferred`, no score.
2. **Weak supervision**: rule-generated candidate signals with provenance.
3. **Human gold/pairwise data**: annotation contracts (see
   [ANNOTATION_SCHEMA.md](ANNOTATION_SCHEMA.md)).
4. **Baseline ML** (e.g. LightGBM/XGBoost) on extracted features.
5. **Neural model / segment-level profiling** while keeping the same public
   interface and JSON schema.

Model internals can change without breaking consumers as long as the schema
and the `SkillProfiler` interface remain stable.
