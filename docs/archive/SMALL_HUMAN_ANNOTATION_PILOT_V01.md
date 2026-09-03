# Small Human Annotation Pilot v0.1

Status: **PREPARED — WAITING FOR ONE REAL HUMAN ANNOTATOR**

```text
SMALL_HUMAN_ANNOTATION_PILOT_PREPARATION: PASS
WAITING_FOR_HUMAN_ANNOTATION: YES
```

## Purpose and boundary

This is the first real annotation experiment for the provisional Active
Learning v0.1 questions. It tests whether one knowledgeable osu!standard
annotator can understand, judge and repeat pairwise comparisons using the
available local presentation.

It is not a training dataset. Human responses are subjective evidence, not
labels or ground truth. This stage does not train a model, freeze a taxonomy,
change Weak Supervision, or analyze answers that do not yet exist.

## Selected batch

The immutable pilot selects 40 tasks from the validated 93-task dry-run batch.
It does not regenerate the 33,796-candidate pool.

```text
tasks:                     40
MAP/MAP:                   10
SEGMENT/SEGMENT:           30
explicit hidden controls:  10 (25%)
ordinary tasks:            30
```

The selection reasons are deliberately mixed:

```text
boundary-adjacent: 10
abstention-heavy:  10
challenge audit:   10
easy anchor:        2
ambiguous control:  2
within-map segment: 2
exact repeat:       2
A/B inversion:      2
```

The three propositions remain provisional:

- `movement_demand_high`;
- `dense_timing_pressure_high`;
- `slider_tracking_travel_high`.

The control manifest is separate from the blind task payload. Exact-repeat and
A/B-inversion controls are separated from their sources by at least 32 tasks;
controls are never adjacent. The presented order is deterministic and never
changes in response to human answers.

## Asset and segment readiness

All 153 maps referenced by the 93-task source batch still have readable `.osu`
files. Two source maps have missing declared audio files, making four source
tasks operationally unavailable for this real pilot. Those tasks are recorded
in `asset_inventory.json` and excluded; no media is fabricated.

Every one of the 40 selected tasks resolves to:

- a content-verified local `.osu` file;
- local audio for both sides;
- real parsed osu!standard hit objects;
- canonical five-second segment identity for SEGMENT tasks.

SEGMENT presentation uses the existing contract: 2,000 ms pre-roll, the
canonical playable window, and 1,500 ms post-roll. MAP tasks present the full
map. Both sides explicitly use NM. The browser renders circles and flattened
slider paths directly from parsed `.osu` geometry, sizes objects from the
map's CS, and animates a slider ball along every real path and repeat span in
sync with local audio. It does not show engineered feature or weak-rule
values. The annotation screen and proposition questions are Chinese; osu!
notation such as NM, CS and BPM remains unchanged.

This is a research visualization, not an osu! gameplay simulator. It does not
reproduce gameplay skin, hit animations or replay cursor movement.

## Blindness policy

The annotator can see only the reviewed proposition question, anonymous entity
IDs, neutral map metadata, NM, local audio and object visualization. Mechanical
validation rejects nested blind payload keys that expose:

- weak evidence or Reference outcomes;
- acquisition scores or selection reasons;
- expected direction;
- control identity or source relationship;
- split/challenge membership;
- mapper/set sampling identities.

## Annotation workflow

From the repository root, prepare/recheck the immutable pilot:

```powershell
python tools/prepare_human_annotation_pilot_v01.py
```

Then start the local runner:

```powershell
python tools/annotation_runner_v01.py
```

Open `http://127.0.0.1:8765/` in a browser. The server binds to loopback only.
For each task:

1. play and inspect A and B;
2. choose one of the six ordinal answers, including `CANNOT_JUDGE`;
3. optionally select a non-probabilistic confidence band or add a short note;
4. explicitly submit the response.

Keys `1` through `6` select answers; Enter submits after a selection. The
annotator can stop the server at any time and resume with the same command.

## Response contract and storage

Responses are stored separately from task definitions under:

```text
training/datasets/active_learning_v01/human_pilot_v01/
  responses/annotator_001/pilot_session_001.jsonl
```

The session file is append-only. Each strict JSONL record preserves task,
source batch, annotator, session, presentation orientation, explicit answer,
UTC response timestamp, elapsed time, optional confidence/reason/note, and
schema versions. A second response for an existing task, out-of-order response,
unknown task, malformed partial line or mismatched session fails closed.

The default pseudonym is `annotator_001`; no unnecessary personal information
is stored. A different session must use a distinct `--session-id` and therefore
a distinct response file. Existing sessions are never silently overwritten.

## Stage B analysis plan

Stage B begins only after a real human completes the session and explicitly
asks the agent to resume. It will first validate provenance and completeness,
then normalize A/B orientation and report:

- completion and `CANNOT_JUDGE` rates;
- strict and directional repeat consistency;
- inversion consistency and ordinal distance;
- anchor directional agreement (never called accuracy);
- response distribution and reliable timing summaries;
- results by provisional proposition and MAP/SEGMENT scope;
- conservative position-bias and presentation-judgeability diagnostics;
- human/weak-evidence comparisons as evidence comparisons, not ground truth.

No Stage B result may automatically authorize taxonomy freezing, model
training, or multi-annotator collection.

## Known limitations

- No real response exists yet, so question judgeability and usability remain
  unknown.
- This is a single-annotator, small-N study.
- The visualization is deliberately minimal and has not been validated as an
  exact replica of osu!stable/lazer gameplay.
- The real Weak Supervision pilot has no directional source conflicts.
- Acquisition weights and weak-rule thresholds are not empirically calibrated.
- Historical `ALV01-UNAVAILABLE-001` remains preserved in the old artifact.

At this point the next action belongs to the human annotator.
