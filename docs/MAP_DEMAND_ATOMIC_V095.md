# Map Demand V0.95

V0.95 is an evidence-separation overlay on frozen V0.92.2. It addresses four
correlated-mechanic failures without globally rescaling the nine-axis profile.

## Identity

- algorithm: `MAP_DEMAND_ATOMIC_V095`
- map demand version: `0.9.5.0`
- schema: `map_demand_v0.9.5.0`
- calibration overlay: `mdoverlay_v095:*`
- replay base: frozen V0.92.2

## Mechanisms

### Reading

High AR is diagnostic-only. It never adds Reading by itself. V0.95 preserves an
evidence-backed baseline and attenuates only unexplained excess above that
baseline. Visible overlap, visible clusters, stacks, relative low AR, and HD
interaction progressively retain the inherited tail.

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
repeated large-to-small micro-correction. Raw jump distance never creates a
specialist floor. Weak evidence can reduce the inherited score by at most 8%.

## Anti-overcorrection invariants

- frozen V0.92.2 replay is byte-for-byte unaffected;
- Jump Aim, Flow Aim, and Finger Control are not rewritten by V0.95;
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
