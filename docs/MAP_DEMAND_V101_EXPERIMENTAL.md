# Flow and Aim Control experiment: 1.0.1-experimental.11 (uncalibrated development candidate)

Revision .11 removes .10's turn-prediction helper and repetition discount.
For verified nonzero circle vectors, directional velocity change is weighted
by `(1 - dot(unit_incoming, unit_outgoing)) / 2` before logarithmic conversion.
Smaller interior angles therefore retain more turning demand; scalar velocity
change is preserved as a lower bound. No angle threshold or per-map multiplier
is used. Zero vectors do not invent an angle; slider direction remains unknown.
Absolute deadlines still express speed, while effort-layer support within
eight movements / three seconds distinguishes locally dense sharp turns from
scattered ones. No separate frequency multiplier was added.

Actual-geometry checks cover increasing sharpness for repeated same-direction
and alternating turns, faster timing, and clustered versus scattered sharp
turns. CS/deadline/support functions and .9 Flow are unchanged. This corrects
the rejected .10 response but is not a completed calibration: Tower Heaven
HDHR is 4.53 versus the earlier human reference 6.4–6.7. Evidence is in
`tmp/control-angle-rate-20260906/`. Production remains .5; no deployment occurs.

The following .10 discussion is retained as rejected historical context.

**Not accepted for deployment:** subsequent angle/frequency probes contradict
the user's sharp-turn constraints. Repeated sharp turns must not be discounted
merely for repeating; the current departure cap can even reduce Control when
alternating turns become sharper. Revision .10 requires rework. Passing tests
and its lower BP aggregate do not establish correct difficulty semantics.
See the latest joint audit and `angle-frequency-check.json` in the .10 evidence.

Revision .10 changes only the Control arrangement hypothesis. Three contiguous,
verified nonzero circle movement vectors define the last signed rotation. The
new vector is compared with continuing that rotation; this departure bounds
the existing vector-change demand from above. Scalar speed-change demand is
preserved. Missing context, sliders and zero vectors retain the previous pair
calculation rather than inventing a trajectory. Initial turns still have
observed demand; constant curvature is not repeatedly counted as a new turning
adjustment. The interpretation remains a hypothesis, not a motor-control law.
Target-size, deadline, support and star-conversion functions are unchanged.
Flow is exactly .9. Local runtime/caches identify .10 / Control 0.4.0 separately.
Current evidence is in `tmp/control-turn-change-20260906/`; no deployment occurs.
Jungle and True DJ become about 6.84 and 7.76, below the rough human references
7.5 and 8.2, so this candidate does not claim absolute calibration is complete.
The revisions below are historical context.

Revision .9 is a coarse calibration candidate. The user supplied Prismatix
4994500 HD ~7.2 as a rough Flow reference. A coarse grid retained the existing
log coefficient 3.5 and changed only the experiment's log gain from 1.55 to 2.0;
it did not solve two free parameters to fit two approximate anchors. Local,
reentry and sustained values use the same conversion. Raw loads, section
selection, geometry, Control and frozen v100 conversion are unchanged.
Prismatix becomes 7.11; this is calibration evidence, not validation accuracy.
Blue Zenith remains 5.64, below the user's 6–7 range. Power's position within
the three new references and Affection versus Tower Acme also remain unresolved.
The zero-load origin and unbounded monotonic response are preserved. No map
IDs or labels enter the scorer. This version remains local and is not deployed.
Evidence: `tmp/flow-scale-20260906/`.

Revision .8 replaces local intensity averaging with a supported intensity-layer
integral. Each layer uses only the movements reaching it, with dominant evidence
bounded by corroborating evidence. Sustained load uses each movement's physical
intensity corroborated by a neighbor, rather than the local window's average.
Direct local corroboration still guards isolated peaks. Compactness can retain
direction evidence but cannot create it at an almost-reversal. Relative timing
also constrains sustained ownership: a longer transfer between faster phrases
has extra adjustment time. A classified non-Flow circle transfer ends accumulation;
unknown local context is not itself such a classification, preserving partial
recovery through a known slider.

This candidate has not established the human star scale. In particular, the user
labels Prismatix 4994500 HD and Snow Goose 4628575 HDHR much harder in Flow than
Blue Zenith 657916 HDHR; Power of the Dragonflame 5211222 HDHR is the easiest of
the three but still harder than Blue Zenith. The latter map has more uniform
difficulty with peaks, correcting the earlier assumption that all three are
mostly easy spacing with one hard section. These are evaluation labels, not
scorer inputs. No global star multiplier has been increased to satisfy them.
Revision .8 is local only; production remains .5. The preceding .7 mechanics
and evidence below are historical context. Current experiments and rejected
ablations are in `tmp/flow-owned-load-20260906/`.

This release can be selected explicitly with `--algorithm v101-experimental`.
The fallback remains `v100`; a saved local runtime override takes precedence.
Its seven axes other than Flow and Aim Control are inherited
unchanged, including under mods. Revision .5 uses whole-transition Control,
absolute target-relative adjustment deadlines and observed CS, and corrects
the spatial-reentry boundary. See `FLOW_CONTROL_JOINT_SCALE_AUDIT_2026-09-05.md`
for development evidence and unresolved constraints. Derived summaries and archetypes are
recomputed after replacing both axes. This experiment is not an absolute-difficulty
calibration or a claim that a target beatmap should have a particular rating.

Revision .6 retains .5 Control and local two-sided Flow direction membership.
For repeated history loss, it uses both neighboring movements' maximum
distance and time: `x = (max_distance / reference_diameter) * (max_time / 150ms)`,
`relief = 1 / (1 + x^4)`. A history link retains `q + (1-q)*relief` instead of
`q`. A zero local direction link still breaks the candidate. The reference
diameter is fixed, so CS changes demand without reclassifying the arrangement.
These references define an uncalibrated hypothesis, not a physiological
reaction time. Tight, closely timed turns lose less preceding evidence;
large separated moves retain almost the previous history discount.

Revision .7 accumulates supported Flow movements using a time-weighted fourth-power
norm (one-second reference), and takes the maximum of sustained and local demand,
not their sum. Each actual movement contributes at most once, including validated
spatial reentry; overlapping local windows cannot multiply its contribution.
Credit is constrained by local Flow ownership and current physical intensity.
Established continuous circle Flow accumulates without recovery merely for being
slower. Known slider travel retains part of the load with a four-second exponential
recovery reference; unknown geometry and structural breaks reset it. Sliders do
not receive circle separation credit.

This is a local candidate, not deployed by this change. The growth exponent,
ownership threshold and recovery references are uncalibrated engineering choices.
Blue Zenith remains low; shared axis calibration is unresolved. The .7 version and
calibration identity prevent future cache reuse across the changed scorer. See
`tmp/flow-sustained-20260906/` for batch results and regression evidence, and
`tmp/flow-low-audit-20260906/` for the preceding local-direction comparisons.

The local BID HTTP service now defaults to three spawned analysis workers
(`--analysis-workers 3`) for WuxinBot BP batches. This runtime change preserves
the .5 scoring and calibration identity; see the 2026-09-06 BP50 runtime section
in the joint audit for cold-cache performance and regression evidence.

## Problem and scope

The frozen Flow model lets directional morphology affect adjacent weight
products, representative velocity, and a final morphology multiplier. Its
48-record window turns more regular evidence into a large difficulty gain.
Conversely, mixed and curved movement can lose substantial representation.

The experiment separates physical movement intensity from the evidence needed
to establish that intensity as Flow. Broad displacement remains an explicit
input alongside its available time. Revision .7 separates continued sustained
burden from bounded local evidence support; the latter does not impose a
physical difficulty ceiling. Its growth magnitude still needs validation.

Revision .2 separates local turn adjustment from chain membership. Revision
.3 adds circle-only spatial phrase reentry during continuous tapping, with no
intervening slider. Mechanism coverage does not validate the magnitude of a
human difficulty gap or establish an absolute star scale.

No beatmap IDs, official total star ratings, PP, BP ranks, human labels, or
requested target scores are used in the scorer.

## Geometry

`flow_geometry_v02.py` is an independent adapter over Local Signal 0.4 rows.
It never changes the historical extractor or a frozen model dependency.

- Directions use previous lazy endpoint to current head, with positions and
  scalar distances checked for consistency.
- Zero vectors do not acquire an angle from signed zero. An exact reversal
  has an unsigned turn of pi but no invented left/right sign.
- A known zero movement can be followed through the nearest nonzero direction
  with explicit elapsed time. Unknown geometry, spinner boundaries, ambiguous
  timestamps, and long gaps cannot join unrelated chains.
- Full-route lazy travel plus exit distance uses full head-to-head time. The
  minimum-distance channel retains its own time and is not mixed into it.
- Slider internal tangents and client stacking are not reconstructed. Exit
  directions remain a jump-phase proxy, not an observed cursor trajectory.

## Physical intensity

For distance `D`, time `T`, observed radius `R`, and the CS4 reference `R0`:

`I = sqrt(D / (2 R0)) * ((D/T) / 0.65)^0.70 * (R0/R)^0.70`

Thus `D/T` is not the only representation of movement. Increasing available
time still reduces load continuously to zero at fixed distance; there is no
distance-only floor. Observed, already-transformed radii are used once.
Mod labels do not reapply HR/DT/HD to existing rows.

The velocity reference/exponent and target-size exponent retain conventions
from the frozen Flow scale. The independent square-root displacement term
follows the existing joint spatial-load form, with a two-reference-radius
distance unit. These are explicit experimental assumptions, not constants
fitted to Affection, Tower, or a desired star interval.

## Direction evidence and support

Absolute turn and elapsed direction time provide chain evidence. Change
between two established turns contributes local control rather than a second
membership penalty. A regular polygon with
90-degree corners must not receive near-perfect Flow membership merely
because its turn changes little from corner to corner.

Within each contiguous 4–32 movement suffix (at most four seconds), an
interior movement needs direction evidence on both sides. Its ownership is
`min(p_in, p_out)` multiplied by the survival of intervening links to the
window endpoint. A zero-membership link splits the chain. Boundaries provide
context and cannot donate unsupported large-jump intensity.

The local estimate is an ownership-weighted mean of movement-plus-control loads.
One exceptional interior maximum is capped at the second highest interior
intensity for the estimate; its raw peak remains diagnostic. This retains
width-varying Flow instead of defining the whole pattern by its smallest step.
Individual movement intensity does not multiply in morphology, but its
representation in an established Flow estimate requires local ownership.

The SAME absolute ownership mass `E=sum(ownership)` establishes support via
`1-exp(-(E/4)^2)`. Consequently tiny ownership cannot disappear through
normalization and claim full support. Weak or disconnected evidence cannot
simply be added across unrelated subchains. All support constants and selection
policies are emitted in diagnostics.

## Local turn adjustment

Each turn is represented as a two-dimensional rotation `q=(dot,cross)` of
successive jump-phase unit vectors. The next turn's adjustment ratio is
`r=||q_current-q_previous||/2`, in [0,1]. This is invariant under reflection
and rotation, and continuous through 180 degrees. The historical signed-turn
field still does not invent a left/right orientation for an exact reversal.

Two direction links wholly inside the current candidate must support this
adjustment: `r_supported = r * sqrt(p_previous * p_current)`. The first
interior movement has no such complete context and receives no adjustment.
Thus a sharp turn outside a candidate cannot donate control difficulty to a
subsequent ordinary Flow chain. The estimated local load is
`I * hypot(1, r_supported)`, before the same isolated-peak and ownership rules.

This orthogonal combination is an explicit **uncalibrated hypothesis**, not a
measurement of cursor acceleration or an addition of whole-map Aim Control
stars. Its geometry is a jump-phase proxy and cannot reconstruct control along
an unseen slider tangent. Diagnostics retain movement-only intensity, the
local increment and supported adjustment ratio. Continuous-Flow candidates
retain `spatial_reentry_classified=false`; the overall signals state that the
additional spatial mechanism is enabled. The raw peak remains movement-only.

## Circle-only spatial phrase reentry

`flow_spatial_reentry_v01.py` exposes raw evidence separately from rating:
each bridge has a unique source identity and alternative left/right contexts
of two to four movements per side. Slider, spinner, zero/missing movement,
nonconsecutive sources, and structural gaps break the circle run. Relative
log-interval changes supply soft continuity evidence without a fixed 2 ms
rhythm gate. Physical times are preserved for actual intensity.

A scored reentry requires spatial clearance above the within-phrase scale
and a boundary rotation change relative to the two phrases. Mere distance
variation or differing mean directions on a regular curve do not suffice.
Each side's forward alignment supplies independent Flow evidence. The gap
and boundary change supply a switch ratio; they do not increase that evidence.

`flow_reentry_execution_v01.py` uses the harmonic mean `A` of the two sides'
local representative movement intensities and the bridge's own intensity `J`.
The bounded interaction is `B=A*J/(A+J)`: increasing bridge execution demand
can increase the extra burden, with an upper bound supplied by both local
inputs. Bridge movement is excluded from those side intensity estimates.
The switch ratio multiplies this additional load. Unique event evidence `E`
establishes reentry support `1-exp(-(E/2)^2)`; even one event can supply finite
support. Multiple views of a bridge and shared phrase movements are not new
repetitions. Extra load is integrated by intensity layer with reference two;
a high layer uses only events whose own bounded control reaches that layer.
An isolated event retains its own finite support without borrowing cheap
events' evidence. There is no discontinuous switch to a second-highest-event
cap when a second, arbitrarily weak event appears.

Reentry also needs a compound Flow baseline: simply reusing the continuous
chain estimate retains the very boundary penalty this mechanism addresses.
Internal phrase links use the harmonic intensity of their two raw movements.
Their quality is positive forward dot times the pair's relative interval
match and whole-candidate cadence evidence. Thus the same internal link has
the same quality in every context. Shared links are counted once; their
activation uses the strongest attributable context. All bridge movements are
excluded. Evidence of the internal Flow is separate from switch activation,
so changing only a bridge's distance cannot change the flanks' link quality.

After capping one isolated link intensity maximum, joint intensity and
activation layers contribute `delta(I) * delta(g) * (1-exp(-(E_Ig/4)^2))`.
Only links reaching BOTH levels supply evidence. Within each joint layer,
the largest quality is bounded by the sum of all other qualities. One strong
link cannot be legitimised by a second source whose quality approaches zero.
For equal-quality, equal-intensity, equal-activation links, this reduces to
`I*g*(1-exp(-(sum(q)/4)^2))`. Activation is applied once, without being
squared inside the evidence response. Adding low activation cannot dilute
existing load, and cheap strong links cannot lend support to expensive weak
links. Zero activation yields zero new load continuously.

The candidate uses the larger of this compound estimate and the weighted
mean of event-owned continuous baselines, then adds event-owned bounded
extra load. Each continuous baseline suppresses previous turn adjustments
involving its bridge vector. No event borrows a whole-map peak. The weakest
adjacent relative interval match across the entire candidate also attenuates
support, including rests between otherwise individually valid contexts.
Another event's bridge cannot occur in its support phrases. Original Flow
and reentry candidates compete by maximum; no whole-map Flow, Aim Control,
Reading, or Raw Speed score is added.

Addition here is an explicit uncalibrated extra-load hypothesis, not a claim
of measured motor cost. A preliminary hypot fusion imposed an additional
quadratic attenuation on an already bounded extra load and was replaced.
Recognition of geometric/rhythmic coordination does not predict actual reading
or tapping errors. Details and validation are in
`FLOW_SPATIAL_REENTRY_EXPERIMENT_2026-09-05.md`.

The final display conversion retains `3.5 * log2(1 + 1.55 * supported_load)`.
Sharing this conversion with v100 does not independently validate the new
absolute star-equivalent scale.

## Validation requirements

Mechanism checks use geometrically consistent circle fixtures, not hand-written
angle fields or target-map score assertions. They cover smooth curves versus
reversals, variable amplitude, timing relaxation, short hard versus long easy
chains, bounded support, isolated large jumps, weak-chain support borrowing,
single-record radius anomalies, mirror/rotation invariance, unavailable
geometry versus observed zero, and separation across gaps/spinners.
Additional checks cover rotation-change continuity through exact reversals,
reflection, missing-history reset, and exclusion of control sources outside
the candidate window.
Spatial checks add short genuine phrases, variable-spacing regular curves,
circle-only filtering, temporal rests and rate changes, finite bridge bounds,
weak-side limits, same-bridge deduplication, overlapping phrase provenance,
and exclusion of an unrelated stronger baseline.
Compound checks isolate intensity-layer evidence, bridge exclusion, overlap
deduplication, and expensive weak links surrounded by cheap strong phrases.

Integration checks compare the full non-Flow axis payloads under NM, HD, HR,
HDHR, EZ, DT and HT. Historical v100/Beta9.2 canonical replay checks remain
unchanged. The runtime override file and existing service are not switched by
installing this experiment.

Real-map comparison must keep source checksums and actual score mods fixed.
Inspect the new winners and the biggest rank changes across a cohort, including
jump maps, rather than accepting an experiment because two chosen maps move in
the desired direction. Human relative-difficulty validation is still required.

## Inspecting results

The new full CLI output contains `diagnostics.v101_flow_execution` with local
execution intensity, raw peak, bounded support, geometry coverage, the selected
section, and separated local sections. `signals.spatial_reentry` preserves
its own best candidate even when a continuous section wins the public axis;
the absence of a public star change does not mean no local event was detected.
Sections are never summed. A raw peak
is diagnostic evidence and is not automatically the public Flow value.

```powershell
python -m tools.map_demand_v01.cli analyze `
  --map 'path/to/map.osu' --mods HD HR `
  --calibration-dir training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k `
  --algorithm v101-experimental --out tmp/flow-experiment.json
```

For an independent review UI, use the README's explicit experiment command on
port 8768. The UI displays the selected release label. On 2026-09-05 the user
requested local activation on the existing port 8767 service; see
`MAP_DEMAND_V101_EXP3_LOCAL_DEPLOY_2026-09-05.md` for the activation record.
