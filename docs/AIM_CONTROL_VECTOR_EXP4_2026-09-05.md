# Aim Control direction repair — 1.0.1-experimental.4

Date: 2026-09-05. This revision addresses the confirmed F01 representation
gap in `GENERALIZATION_AUDIT_REVIEW_2026-09-05.md`. It preserves Exp3 Flow
and the seven other v100 axis payloads. Frozen extraction, calibration data
and v100 dependencies are unchanged.

## Target fixed before implementation

The user explicitly selected **最难局部的控制需求**: the hardest locally
established demand for accurately executing aim control. It is neither a
whole-map average, nor a player-performance or FC-probability prediction.
The computational proxy uses at most eight consecutive control opportunities
within three seconds, including the full source interval of the first pair.
This window and the support reference below are experimental assumptions;
they are not human-validated constants.

## What was missing and what changed

The former Control compared distance, scalar speed and cadence. All three
changes vanish at constant distance/time, regardless of direction. The new
adapter verifies circle-to-circle vectors against both HEAD_FULL and
MINIMUM_MINIMUM distance/time. A control opportunity requires two consecutive
verified transitions, hence three circles. Mod-transformed positions are
used with their already adjusted times; no Mod multiplier is applied twice.

For matched average velocity vectors `u`, `v` and their scalar magnitudes
`a`, `b`, the speed-change term becomes:

`log2(1 + ||v-u|| / (min(a,b) + 0.12))`

For same-direction collinear movement this is algebraically equal to the
previous `abs(log2((b+0.12)/(a+0.12)))`. A turn now contributes even when
the speed magnitudes match. There is no extra Flow score, map identity,
official SR, PP, BP rank, human score or desired star target in this term.
The original spacing/cadence weights, movement-presence term and deadline
exponent are retained. The vector expression remains a relative change
measure: it saturates with absolute speed at a fixed angle. It is not a
measurement of player acceleration or a complete motor-control model.

The extractor clamps positive intervals below 25 ms to 25 ms. The adapter
uses that same adjusted phase and records clamping; it does not call this
the actual cursor execution time. Nonpositive/equal timestamps remain
structural separators. A known zero velocity vector is available evidence;
it does not acquire a made-up direction angle. The inherited pair-presence
term still suppresses pairs with a stationary movement. Start/stop modelling
has not been added in this repair.

## Establishing a local level without borrowing weak evidence

The old score averaged the highest six efforts in an eight-opportunity
window and applied a map-independent evidence multiplier with a positive
floor. The new score integrates support independently at each effort level:

`L = integral_0^max(effort) [1 - exp(-(N(effort >= level)/3)^2)] dlevel`

`Control = 5 * log2(1 + 1.50 * L)`

Only opportunities that reach a given level support that level. A weak
neighbour cannot give a high outlier full support. Repeating an established
section elsewhere cannot multiply the local maximum. The eight-opportunity
limit and three-second source-span limit apply together. Adjacent triples
overlap: they are distinct adjustments, **not statistically independent
human observations**.

This is also an aggregation change, so a rating increase cannot all be
attributed to the direction repair. `scalar_only_same_aggregation` re-scores
the same records using the original scalar effort. It provides an explicit
ablation separating vector representation from aggregation.

## Missing mechanisms are not zero demand

The minimum slider distance combines tolerance-adjusted lazy/tail candidate
distances without preserving the selected endpoint. Its time also deducts
slider travel. A head or lazy vector therefore cannot safely supply the
missing minimum-phase direction. This revision retains observed scalar
morphology at these opportunities and marks direction unavailable.

The output separately reports scalar and direction coverage over the map,
plus direction coverage of the winning local window. Partial direction
coverage gives `DEGRADED` for positive observed demand and leaves global
counterevidence null. A zero scalar result with missing direction is
`INSUFFICIENT`, with a null public value, rather than an observed Control
zero. `FULL` means all defined mechanisms are observed in this model;
confidence remains LOW and does not assert that every human mechanism is
represented. Missing positions, phase mismatches and unsupported sliders
have separate reasons.

Unlike the former global 80% coverage veto, incomplete evidence elsewhere
does not suppress an observed positive local maximum; the result remains
explicitly partial. Public magnitudes at or below `1e-12` are treated as
numerical zero, so roundoff after a rigid rotation cannot turn missing
direction into positive observed demand. Raw effort diagnostics are retained.

The BID workbench displays the local time range and incomplete-direction
notice. Its fill-from-model action skips null values, so insufficient
evidence is not converted to a human rating of zero.

## Actual pipeline regression

An immutable copy of the Exp3 source package and eleven complete baseline
payloads is under `tmp/control-direction-exp3-baseline/`. Candidate output is
under `tmp/control-exp4-final-regression/` (the first pass is retained in
`tmp/control-direction-exp4-regression-01/`). All eleven final runs preserve
the complete Exp3 Flow payload and seven complete v100 axis payloads; the
frozen v100 nine-axis results also remain identical.

| Case | Exp3 Control | Exp4 Control |
| --- | ---: | ---: |
| 80 px / 100 ms, regular 90-degree turns | 0.000000 | 4.406290 |
| Same distances/times, irregular turns including reversals | 0.000000 | 4.703888 |
| 40/160 px spacing positive control | 7.005266 | 8.448795 |
| Affection HDHR | 5.205040 | 7.692730 |
| Tower Of Heaven [Acme] HDHR | 5.075092 | 6.460965 |
| Altar NM | 4.644691 | 6.907418 |
| Lunatic Sky [LUNATIC] NM and HD | 4.817648 | 7.429774 |

The synthetic cases use real `.osu` files and the complete formal pipeline,
each under NM and HDHR. They show that the directional counterexample is
resolved; they do not establish that 4.41 or 4.70 is the correct human star
rating. The real-map rows are development/regression cases, not blind labels.
Affection's previous Flow comparison does not provide a numerical Control
target. No parameter was fitted to this table.

For the same aggregation, removing only the vector extension gives Affection
6.54354, Tower 6.40502, Altar 6.33653 and Lunatic Sky 7.00187. These ablations
can choose different winning windows; their differences are not separately
additive physical skill components. In particular, Tower's increase is
mostly an aggregation effect, not newly observed direction demand.

The existing BP100 snapshot was separately re-extracted with its actual Mods
using the local-signal path. All 100 Control calculations completed; all are
honestly marked partial because their slider opportunities include uncovered
direction. This is a coverage/result audit, not 100 full nine-axis runs or
human accuracy validation. Full records, scalar-only ablations, source and
map hashes are in `tmp/control-exp4-final-bp100/`; the first pass remains
under `tmp/control-exp4-bp100/`. Final numerical results agree with the first pass.

## Remaining audit items

- F01: the circle direction representation and missing-mechanism semantics
  are repaired. Slider direction/tangents, stopping behaviour and absolute
  calibration remain outside this revision.
- F04: the Control target is now fixed and its source-window aggregation
  explicit. This does not require every other axis to use the same window.
- Independent human validation: reuse the existing retest framework with
  blinded values, family-separated material and this frozen question. Known
  Affection/Tower/Lunatic/F01/BP cases remain development material. Prepared
  materials or automated tests are not completed human responses.
- F02 Reading long motifs, F03 shape-specific tolerance response and F05 a
  common human scale remain open. This repair does not change their formulae
  or claim to solve them by shifting another axis's ratings.

Final validation: **964 tests run, 961 passed, 3 existing optional real-corpus
tests skipped**, 95.044 seconds. This includes 32 independent Control tests
and five isolated PowerShell restart-selection tests. Six historical tests
had still asserted the former hardcoded restart parameter default; these
were updated to retain release registration checks, with selection behaviour
tested directly in a temporary repository. Frozen model outputs were not
changed to satisfy those tests.

See `MAP_DEMAND_V101_EXP4_LOCAL_DEPLOY_2026-09-05.md` for the final source
hashes and live-service checks. The independent review is
`tmp/CONTROL_VECTOR_V01_INDEPENDENT_REVIEW.md`; blinded pilot/candidate
materials and explicit remaining prerequisites are in
`tmp/control-direction-blind-v01-ready/PLAN.md`.
