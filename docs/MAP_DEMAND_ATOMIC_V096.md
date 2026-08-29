# Map Demand V0.96

V0.96 is a signed-evidence overlay on frozen V0.95.3. Its purpose is profile
contrast: an axis must be allowed to move down when the map contains evidence
against that mechanic, while decisive mechanic evidence may move an axis above
the total-SR anchor.

## Identity

- algorithm: `MAP_DEMAND_ATOMIC_V096`
- map demand version: `0.9.6`
- schema: `map_demand_v0.9.6`
- calibration overlay: `mdoverlay_v096:*`
- replay base: frozen V0.95.3

## Scoring policy

Each axis records three independent values:

1. `support_gate`: structural evidence for the mechanic;
2. `counterevidence_gate`: structural evidence that the mechanic is absent or
   materially easier than the map's main demand;
3. `prominence_gate`: a convex uplift reserved for decisive support.

The previous V0.95.3 value is retained only as a bounded continuity reference.
It is not an exact human target and cannot veto strong counterevidence. Total SR
scales a mechanic after the mechanic is established; it is not a universal
minimum for every axis.

## Mechanism changes

### Micro Precision

The stable key remains `spatial_precision`. Target size is now signed around
the effective CS4 radius:

- small targets add tolerance pressure;
- large targets add explicit relief;
- fast settling and repeated large-to-small correction add independent support.

Therefore a high-star large-circle map can have materially lower Micro
Precision than a low-star small-circle map. A large target does not erase real
micro-correction evidence, but total SR alone cannot create Precision demand.

### Jump Aim and Aim Control

Jump Aim uses distance-speed severity, persistence, extreme-tail activation,
and the broad share of genuinely large movements. It no longer waits for the
extreme tail to activate before recognising ordinary high-level jump demand.
Aim Control uses movement-state changes; stable large jumps are explicit
counterevidence instead of automatic control demand.

### Raw Speed and Finger Control

Raw Speed requires a compact fast-tapping peak plus chain persistence. A short
high-BPM section or high-BPM jump cadence cannot receive the same support as a
long repeated tapping chain. Finger Control receives support from repeated
non-trivial local interval changes; regular rhythm is counterevidence, but the
older score remains a moderate reference because the current novelty detector
is intentionally conservative.

### Flow, Reading, Stamina and Endurance

- Flow support combines smooth chain morphology and repeated pressure;
  disconnected or non-persistent movement is counterevidence.
- Reading support combines pair-supported visibility conflict, activity,
  relative low AR and HD interaction. High AR with sparse, clear presentation
  is relief, not positive evidence.
- Stamina and Endurance use pressure duration, coverage, repeated sections and
  recovery. Short or rest-heavy maps receive negative evidence. Duration uses
  diminishing returns.

## Human-review policy

Human ratings are no longer exact fitting targets. They are used as:

- broad `±1★` plausibility bands;
- within-map ordering constraints when two human ratings differ by at least
  `0.75★`;
- qualitative checks for dominant and suppressed mechanics.

Exact MAE remains diagnostic-only. Old annotations may use earlier axis
definitions and therefore cannot define V0.96 ground truth.

## Validation

```powershell
python -m unittest tests.test_map_demand_v096 tests.test_map_demand_v095 tests.test_map_demand_v092
python tools/compare-map-demand-v095.py 4385157 4288226 2809623 5648807
python tools/evaluate-map-demand-v095.py
```

The comparison scripts read private local reviews and Songs data at runtime;
they do not publish those records. V0.95.3 and all earlier algorithms remain
replayable.
