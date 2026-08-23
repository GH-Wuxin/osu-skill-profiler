# Map Demand Atomic V0.9 — Finger pattern and structural visibility

`MAP_DEMAND_ATOMIC_V07` is a mechanism overlay on the replayable V0.8
nine-axis model. It preserves the `atomic_v0.8.0` human-label taxonomy and the
V0.8 Stamina / Endurance split.

Versioned identities:

- algorithm: `MAP_DEMAND_ATOMIC_V07`
- output schema: `map_demand_v0.9.0`
- axis schema: `atomic_v0.8.0`
- overlay calibration identity: `mdoverlay_v09:*`

## Finger Control

V0.8 relied partly on map-wide interval entropy and reduced its tapping floor
by circle share. That missed demanding slider/circle mixed passages and could
confuse globally varied song rhythm with locally difficult finger patterns.

V0.9 extracts adjacent non-spinner intervals inside fast passages (both
intervals at most 250 ms). Finger Control can rise only when one of these
conditions holds:

- the passage repeatedly alternates short and long intervals;
- softer interval variation persists through a long fast passage;
- softer variation occurs in a locally dense, relatively short map.

Regular fast streams remain governed by the V0.8 result. The overlay records
the interval-change gates, speed-floor recovery, sustain and density bonuses
in axis evidence.

## Reading and HD

V0.9 does not add a flat HD premium. A Reading correction requires either:

- preempt above 540 ms in a moderate/high physical environment; or
- HD combined with high local P95 density.

Low AR and HD compound each other. The correction fades at the extreme tail,
where V0.8's explicit relative-AR mechanism already applies, preventing the
same visibility deficit from being counted twice.

## Stamina

Stamina receives a bounded local-P95-density correction below the validated
high-intensity region. The correction fades to zero around 7.2/10 and remains
capped at 10. Map duration is not used; whole-map duration and volume remain
Endurance signals.

## Assisted-review replay

Thirteen V0.8 BID reviews were replayed. Four were complete acceptance copies;
the remaining records contain targeted human changes. On axes where the human
value differed from V0.8 by at least 0.15, mean absolute error changed as
follows:

- Stamina: `0.814 -> 0.081` (3 ratings);
- Finger Control: `2.206 -> 0.142` (4 ratings);
- Reading: `1.387 -> 0.393` (5 ratings).

This is an assisted small-N anchor check, not an independent validation set.
V0.9 therefore keeps heuristic evidence tags and must be checked on additional
maps before fitting or freezing coefficients.

## Commands

```powershell
# V0.9 default
python tools\map_demand_v01\cli.py analyze --map <map.osu>

# Explicit replay
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v08
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v07
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v06
```
