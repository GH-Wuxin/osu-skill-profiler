# Reference full-corpus SHA256 transcription errata v0.1

Status: **PROVENANCE CORRECTION; NO SEMANTIC CHANGE**

`docs/PRE_ML_FOUNDATION_REMEDIATION_V01.md` transcribed the Reference v0.2
full-corpus artifact SHA256 with one extra `E` after `...AAFC`:

```text
historical report text (invalid; 65 hexadecimal characters):
425B05DD1672305F0BD768E3591AAFCEBA9A08B75F5D844656899C4E1F1A86A19
```

The actual artifact has this valid 64-character SHA256:

```text
training/datasets/reference_signal_qa_v02/reference_qa_full.jsonl
425B05DD1672305F0BD768E3591AAFCBA9A08B75F5D844656899C4E1F1A86A19
```

The independent blocker recheck recorded the same correction and found the
artifact coherent with its compact report, 126,509-row identity, corrected
128/128 golden evidence, and Local geometry-blocked totals. This erratum does
not alter Reference Signal v0.2 semantics or historical report bytes. Both the
original transcription and corrected value remain visible here for audit.

Authoritative review: `docs/RED_TEAM_BLOCKER_RECHECK_V02.md`, section
"Completed corpus evidence (supporting only)".
