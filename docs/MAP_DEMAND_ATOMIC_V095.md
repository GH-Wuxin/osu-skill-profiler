# Map Demand V0.95

V0.95 is an evidence-separation overlay on frozen V0.92.2. It addresses four
correlated-mechanic failures without globally rescaling the nine-axis profile.

## Identity

- algorithm: `MAP_DEMAND_ATOMIC_V0953`
- map demand version: `0.9.5.3`
- schema: `map_demand_v0.9.5.3`
- calibration overlay: `mdoverlay_v095:*`
- replay base: frozen V0.92.2

## Mechanisms

### Reading

High AR is diagnostic-only. It never adds Reading by itself. V0.95.3 preserves
the established physical baseline and attenuates only unexplained excess above
it. A high per-object overlap load is no longer sufficient: visible overlap and
cluster pressure must also be supported by the share of simultaneously visible
pairs that actually overlap. This correction is bounded so existing ordering is
preserved. Relative low AR and HD interaction retain the inherited tail only
when density, physical environment, or actual visibility conflict establishes
meaningful activity. Low-demand maps also abstain from inventing a dominant
axis when the general demand anchor is below two stars.

### Raw Speed

Raw Speed requires compact circle-to-circle fast tapping with repeated or burst
evidence. Large-distance jump cadence is a routing signal for Jump Aim, not a
second tapping reward. The correction is conditional on both weak compact
tapping evidence and high large-jump share, and is capped at 15%.

### Aim Control

The V0.95 state timeline measures changes in velocity, spacing, cadence, and
turn state. Absolute turn severity is no longer the dominant term. The emitted
score remains close to the human-checked V0.92.2 ordering unless either:

1. persistent high Jump Aim and a high large-jump share establish a clear jump
   specialist with weak spacing/control evidence; or
2. strong repeated state changes and spacing separation establish a tech
   specialist, where only a small recovery is permitted.

### Micro Precision

The stable axis key remains `spatial_precision`; the display name is **Micro
Precision**. Its evidence is small-target tolerance, rapid settling, and
repeated large-to-small micro-correction. Target tolerance follows a convex CS
curve, so CS7 to CS8 costs more correction room than CS4 to CS5. The resulting
floor remains scaled by total map difficulty, preventing a low-star high-CS map
from becoming a high-star Precision specialist.

### Persistent Flow and Stamina

Flow Aim receives only a small recovery when flow morphology, compact tapping,
and repeated-section duration agree. Stamina is recomputed after physical-axis
separation and receives a bounded recovery only for repeated compact stream
pressure. A short burst or large-jump cadence cannot trigger either recovery.

## Anti-overcorrection invariants

- frozen V0.92.2 replay is byte-for-byte unaffected;
- Jump Aim and Finger Control are not rewritten by V0.95;
- Flow recovery requires persistent compact stream evidence and remains capped;
- Reading overlap correction cannot replace more than 45% of unsupported
  legacy visibility load;
- high values with matching evidence are preserved;
- `Crystalia +HDDT` remains effectively stable across V0.92.2/V0.95;
- `ENERGY SYNERGY MATRIX` retains high Aim Control tech evidence;
- `Lionheart` retains its established Precision ordering instead of collapsing;
- aggregate score shifts are audited against local human reviews without
  publishing those private records.

## Validation tools

```powershell
python -m unittest tests.test_map_demand_v095 tests.test_map_demand_v092
python tools/compare-map-demand-v095.py 4385157 4288226 1475722 2872154
python tools/evaluate-map-demand-v095.py
```

The comparison and evaluation tools read local private datasets at runtime but
do not embed or copy them into the repository.
