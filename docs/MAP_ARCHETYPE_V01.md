# MAP_ARCHETYPE_V01

`MAP_ARCHETYPE_V01` converts the six continuous Map Demand axes into a
deterministic, multi-label map-shape proposal. It is not a human label model.

## Contract

- Overall demand (`LOW`, `MODERATE`, `HIGH`, `EXTREME`) is separate from shape.
- Shape can be balanced, one dominant axis, a named two-axis combination, or a
  generic hybrid of up to three co-dominant axes.
- Missing inputs fail closed. At least four emitted axes are required.
- The policy reads Map Demand outputs only. It does not read reference signals,
  player data, replays, or human labels.
- Thresholds and evidence are emitted with every result under
  `HEURISTIC_RELATIVE_DOMINANCE_V01`.

The implementation is in `tools/map_demand_v01/archetype_v01.py`. Single-map
`analyze` output includes a top-level `archetype` object. This bumps the Map
Demand output contract to `map_demand_v0.3.0`.

## Canonical 5k distribution gate

Run:

```powershell
python tools/skill-profiler-map-demand-v01.py archetype-qa
```

This streams the compact canonical calibration samples. It does not re-read the
10+ GB full Local Signal artifact. The command writes per-map proposals, an
aggregate distribution report, and a 60-task blind human-review package under
`training/datasets/map_archetype_v01/`.

Distribution QA can expose collapse or missing-input defects. It cannot establish
semantic correctness. In particular, the balanced/dominant boundaries require a
human who understands osu!standard map patterns.

## Human boundary

The reviewer uses a local Chinese page that shows neutral map metadata and the
referenced `.osu` path, but never the algorithm prediction. Start it with:

```powershell
python tools/skill-profiler-map-demand-v01.py archetype-review-ui
```

After playing the map, the reviewer rates aim, precision, speed, stamina, rhythm,
and reading on six required integer sliders from 0 to 10. Untouched defaults
cannot be submitted. Cannot-judge remains an explicit alternative. Responses are
validated and atomically stored in `human_responses.jsonl`; manual JSON editing is
not part of the workflow.

For exploratory comparison, start with `archetype-review-ui --show-algorithm`.
That mode reveals the algorithm's six axis scores, archetype, demand tier, and
confidence alongside the human sliders. Sliders do not inherit machine values.
Responses saved there are tagged `ASSISTED_ALGORITHM_VISIBLE`; the evaluator
reports them separately and never treats them as blind validation evidence.

After labeling, run:

```powershell
python tools/skill-profiler-map-demand-v01.py archetype-review-eval
```

The evaluator rejects unknown tasks, malformed answers, invalid axes, conflicting
special answers, and duplicate task/reviewer pairs. Its agreement metrics are
descriptive only; accepting or changing the heuristic thresholds remains an
explicit reviewed policy decision with a version bump.

Full-corpus classification is intentionally deferred until this human calibration
step. Running 126k maps before validating the decision semantics would produce
more guesses, not more evidence.
