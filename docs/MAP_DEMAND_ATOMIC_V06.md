# Map Demand Atomic V0.8 — Stamina / Endurance split

`MAP_DEMAND_ATOMIC_V06` extends V0.7 from eight to nine axes. V0.6 and V0.7
remain replayable and their outputs are not reinterpreted.

Versioned identities:

- algorithm: `MAP_DEMAND_ATOMIC_V06`
- output schema: `map_demand_v0.8.0`
- axis schema: `atomic_v0.8.0`
- archetype schema: `map_archetype_v0.5.0`
- overlay calibration identity: `mdoverlay_v08:*`
- distribution QA: `map_demand_qa_v08_stamina_endurance_20k`

## Semantic split

### Stamina

Stamina now means maintaining execution quality inside a high-intensity
section. Its inputs are:

- the top two non-Stamina physical demands;
- the longest 125/250 ms burst-duration proxy;
- object density.

The time contribution saturates at approximately 20 seconds. A 400-second
stream can have higher Endurance than a 20-second stream, but it does not gain
hundreds of percent more Stamina merely because it continues longer. Stamina
uses a bounded 0–10 human-demand scale and is no longer presented as an
unbounded star-equivalent physical axis.

### Endurance

Endurance means maintaining attention and execution across the whole map. It
combines:

- logarithmic active duration;
- logarithmic object volume;
- a physical-difficulty gate;
- dense-section coverage and density.

It also uses a bounded 0–10 human-demand scale. Long easy maps can express
moderate Endurance; long, dense, difficult and uniform maps approach 10.

## Existing-label caveat

All pre-V0.8 human `stamina` labels were collected before this semantic split
and may include what is now Endurance. They remain valuable context, but are
not exact V0.8 Stamina targets. New BID reviews store a ninth `endurance`
rating under `atomic_v0.8.0`.

## Validation snapshot

The frozen 20k NM audit completed with zero missing feature joins:

- V0.7 Stamina median / p99 / max: 3.78 / 7.44 / 13.35;
- V0.8 Stamina median / p99 / max: 3.64 / 7.53 / 10.00;
- Stamina values above 10: 3 before, 0 after;
- Endurance p10 / median / p90 / p99 / max: 2.32 / 3.98 / 6.56 / 8.69 / 10.00.

Selected unlabelled Endurance proposals:

- Crimsonic dimension: Stamina 7.04, Endurance 9.82;
- Thousandth Sky HD: Endurance 9.23;
- Heat abnormal NM/HD: Endurance 7.57 / 7.67;
- Toosenbou NM: Stamina 3.10, Endurance 3.93;
- Unbreakable Heart HDDT: Stamina 3.78, Endurance 3.48.

These Endurance values have not yet received human ratings. They are the next
review target, not ground truth.

## Commands

```powershell
# V0.8 replay (V0.9 is now the default)
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v08

# Historical replay
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v07
python tools\map_demand_v01\cli.py analyze --map <map.osu> --algorithm v06

$env:PYTHONPATH='tools'
python -m map_demand_v01.evaluate_v08_anchors
python -m map_demand_v01.qa_v08_corpus
```
