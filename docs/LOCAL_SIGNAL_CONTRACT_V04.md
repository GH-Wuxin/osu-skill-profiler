# Local Signal Contract v0.4

Local Signal v0.4 is a geometry-correctness release.  All v0.3 timing,
repeat-count, nested-object, missing-value and 5-second summary semantics stay
unchanged unless stated below.  Local v0.2 and v0.3 remain explicitly
replayable.

## Compound Bezier decoding

For legacy `B` sliders, an adjacent duplicate control point with at least one
following point is a red-anchor boundary.  Local v0.4 splits the path there,
flattens each Bezier segment independently, joins the flattened segments, and
only then applies the beatmap's expected pixel length.

A duplicate pair ending at the final control point is not a segment boundary,
matching the pinned legacy decoder.  Local v0.2 and v0.3 retain the historical
single-Bezier interpretation for byte-replay compatibility.

This correction can change tick positions, tail position, lazy end/travel,
minimum jump distance and slider-aware angle.  It does not change the raw
start-to-start jump distance.

## Reference boundary

Official Reference Signal v0.2 remains frozen on Local v0.3.  Adopting Local
v0.4 geometry in reference signals requires a separately versioned Reference
release; no historical reference identity is silently changed here.
