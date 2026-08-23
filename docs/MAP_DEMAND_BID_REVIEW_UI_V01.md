# Map Demand BID Review UI V0.1

This local workbench shortens the human-review loop to:

1. enter a beatmap ID (BID);
2. resolve the matching `.osu` file from the frozen standard manifest;
3. select NM or a supported Mod combination and run Map Demand V0.9;
4. compare the nine machine scores with human ratings;
5. append the review to an auditable JSONL file.

## Start

From the repository root:

```powershell
python tools\map_demand_v01\cli.py bid-review-ui
```

The default address is `http://127.0.0.1:8767/`. Use `--no-open` to avoid
opening a browser automatically.

The default local inputs are:

- manifest: `training/datasets/std_manifest.json`
- Songs root: `G:/osu! 20210821/Songs`
- star database: `G:/osu! 20210821/osu!.db`
- calibration: `training/datasets/map_demand_calibration_v04_unbounded_star_scale_20k`

The V0.9 result has its own deterministic `mdoverlay_v09:*` calibration
identity and retains the `atomic_v0.8.0` nine-axis human-label schema. Saved
responses bind the exact algorithm version, so V0.8 and V0.9 machine snapshots
remain distinguishable without fragmenting compatible human labels.

Override them with `--manifest`, `--songs-root`, `--osu-db`, and
`--calibration-dir` when needed. `OSU_SONGS_ROOT` is also supported.

## Human rating semantics

- **Approximate** means the submitted number is the reviewer's best estimate.
- **At least** means the map requires no less than the submitted number, but
  the exact upper value is uncertain.
- Disabled dimensions are stored as `SKIP`, so partial reviews are valid.
- Machine results at or above 15 stars display as `15+`; the raw unbounded
  diagnostic value remains in the saved evidence snapshot.
- Stamina and Endurance use a bounded human-demand scale and display as `/10`,
  not as star-equivalent values. Their sliders therefore stop at 10.

Reviews are append-only at:

`training/datasets/map_demand_bid_review_v01/human_responses.jsonl`

Every response binds the BID, local map metadata, machine-axis snapshot,
algorithm identity, calibration identity, reviewer ID, timestamp, qualifiers,
confidence, and notes. The browser cannot submit a filesystem path or replace
the machine analysis snapshot.

## Mod review

The page exposes three independent groups:

- difficulty: NM, EZ, or HR;
- visibility: HD on or off;
- speed: 1.0x, HT, or DT.

This permits combinations such as HDHRDT while making EZ/HR and HT/DT
conflicts impossible in the UI. The server still validates every request,
normalizes the Mod identity, applies difficulty/timing/visibility transforms,
and binds `requested_mods`, `effective_mods`, and `clock_rate` to the saved
response. The displayed local osu! star rating remains explicitly labelled NM;
the nine Map Demand axes are recomputed for the selected Mods.

FL is intentionally excluded because its demand belongs to the deferred
Flashlight-specific dimension rather than the current nine-axis transform.
