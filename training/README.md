# training/

This directory is a reserved layout for the future data-science workflow. It
is intentionally empty of data: this project does not commit beatmaps, derived
datasets, splits, or weak-label files into the repository.

Planned layout:

    training/
      datasets/     -> generated dataset manifests and extracted feature tables
      splits/       -> deterministic train/test split artifacts
      weak_labels/  -> weak-label outputs with provenance (never ground truth)

The split strategies and manifest format live in `src/osu_skill_profiler/dataset/`;
weak-label generation lives in `src/osu_skill_profiler/weak_supervision/`.

## Corpus pipeline

`tools/corpus_pipeline.py` provides a deterministic, dependency-free pipeline
for the local beatmap corpus. It never produces skill labels; the manifest is
a data contract for future dataset work.

```text
scan      lenient full-corpus scan (cheap regex/line counts, resumable)
select    build an adversarial + stratified sample for parser QA
qa        strict parser QA through the full profiler pipeline
manifest  generate the full standard-mode manifest with SHA-256 + strict parse
```

Exact commands used for the current corpus (`G:\osu! 20210821\Songs`):

```powershell
python -u tools/corpus_pipeline.py scan --list <paths.txt> --root 'G:\osu! 20210821\Songs' --out training/datasets/corpus_scan.jsonl
python -u tools/corpus_pipeline.py select --scan training/datasets/corpus_scan.jsonl --out training/datasets/qa_sample_paths.txt --max-total 3000
python -u tools/corpus_pipeline.py qa --paths training/datasets/qa_sample_paths.txt --out training/datasets/parser_qa_r3.jsonl
python -u tools/corpus_pipeline.py manifest --scan training/datasets/corpus_scan.jsonl --root 'G:\osu! 20210821\Songs' --out training/datasets/std_manifest.json
```

### Current corpus results

- 134,554 `.osu` files; 126,533 classified Standard (mode 0 or legacy no-Mode).
- Parser QA (3,000 adversarial samples: all no-Mode legacy maps + timing/SV/slider
  extremes + stratified random): 2,999 passed; the only failure is a 0-byte
  corrupt file (`Ave Mujica - Alter Ego ... [Pretender].osu`). Zero non-finite
  feature values; 17 samples carry flagged large/degenerate derived values.
- Full manifest: 126,509 successful records, 24 documented failures
  (23 files with no hit objects, 1 empty/corrupt file), 153.1 MB.
- `load_manifest()` validates the file; a seeded 2,000-sample checksum
  re-verification passed with 0 errors.
- `beatmapset_id` is present for 105,155 records and missing for 21,354;
  `local_set_group` (the Songs subfolder) is recorded for every record so
  set-disjoint splits can fall back to it when metadata IDs are absent.
- The 24 documented failure files were moved on 2026-08-10 to
  `G:\osu! 20210821\_broken\` (mirroring their original relative paths) so a
  future rescan of `Songs` does not re-classify them. The manifest and
  `std_manifest.failures.jsonl` keep their original locations as the record.

### Caveat: years

The stats file's `mtime_year` is the file's copy/modification time, **not** the
map's creation year (the whole corpus was copied in 2021/2025/2026). The usable
era proxy in the manifest is `format_version` (v3/v4 ≈ 2007-2008, v14 ≈ modern).

## Feature QA (R1)

`tools/feature_qa.py` runs the full chain
(parse -> normalize -> 106 features (Feature 0.2.0) -> fixed-5s segments ->
aggregate) over
deterministic stratified samples, then expands to the full corpus. It never
produces skill labels and never drops or clips anomalies.

```powershell
python -u tools/feature_qa.py run --phase 5k --manifest training/datasets/std_manifest.json --scan training/datasets/corpus_scan.jsonl --failures training/datasets/std_manifest.failures.jsonl --root 'G:\osu! 20210821\Songs' --out-dir training/datasets/feature_qa --workers 8
python -u tools/feature_qa.py run --phase 20k ...   # only after 5k PASS
python -u tools/feature_qa.py run --phase full ...  # only after 20k PASS
```

Results live in `training/datasets/feature_qa/` (`feature_stats_{phase}.json`,
`feature_correlations.json`, `feature_outliers.jsonl`, `slow_maps.jsonl`,
`segment_stats.json`, `FEATURE_QA_REPORT.md`). R1 verdicts: 5k PASS, 20k PASS,
full PASS (126,509/126,509 maps, 0 NaN/Inf, 0 consistency failures).

Two feature-definition issues found and fixed during R1 with regression tests:

- `difficulty.AR/OD/CS/HP` looked up parser keys `ApproachRate/...` by short
  names, so all four features were always `None`; the extractor now maps the
  schema names to the parser's field names.
- `FixedTimeWindowStrategy` assumed hit-object file order equals time order;
  one Aspire map had an out-of-order object, making segment index spans
  overlap. The segmenter now works on a time-sorted view so fixed windows are
  a true partition (regression test added).

Pathological/Aspire-like maps are flagged (`pathological`, `aspire_like`) and
kept in the stats; the full-corpus correlations are computed on the
deterministic 20k nested subset to keep the pairwise pass bounded.
