"""Future human annotation contracts (schema + validation only)."""

from __future__ import annotations

ABSOLUTE_VALUES = ["none", "low", "medium", "high", "dominant"]
PAIRWISE_VALUES = ["a_much_higher", "a_higher", "similar", "b_higher", "b_much_higher"]

ANNOTATION_SAMPLE_SCHEMA = {
    "type": "object",
    "required": ["annotation_id", "skill", "annotator_id"],
    "properties": {
        "annotation_id": {"type": "string", "minLength": 1},
        "skill": {"type": "string", "minLength": 1},
        "annotator_id": {"type": "string", "minLength": 1},
        "beatmap_id": {"type": ["integer", "null"]},
        "beatmapset_id": {"type": ["integer", "null"]},
        "mapper": {"type": "string"},
        "reference": {"type": "string"},
    },
}

ABSOLUTE_ANNOTATION_SCHEMA = {
    "allOf": [ANNOTATION_SAMPLE_SCHEMA],
    "required": ["value"],
    "properties": {"value": {"enum": ABSOLUTE_VALUES}},
}

PAIRWISE_ANNOTATION_SCHEMA = {
    "allOf": [ANNOTATION_SAMPLE_SCHEMA],
    "required": ["a_ref", "b_ref", "value"],
    "properties": {
        "a_ref": {"type": "string"},
        "b_ref": {"type": "string"},
        "value": {"enum": PAIRWISE_VALUES},
    },
}

SEGMENT_ANNOTATION_SCHEMA = {
    "allOf": [ANNOTATION_SAMPLE_SCHEMA],
    "required": ["value"],
    "properties": {
        "segment_index": {"type": ["integer", "null"]},
        "segment_range": {
            "type": ["object", "null"],
            "required": ["start_ms", "end_ms"],
            "properties": {
                "start_ms": {"type": "number"},
                "end_ms": {"type": "number"},
            },
        },
        "value": {"enum": ABSOLUTE_VALUES},
    },
}

ANNOTATOR_SCHEMA = {
    "type": "object",
    "required": ["annotator_id", "reliability"],
    "properties": {
        "annotator_id": {"type": "string", "minLength": 1},
        "reliability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "notes": {"type": "string"},
    },
}

BLIND_REPEAT_SCHEMA = {
    "type": "object",
    "required": ["repeat_group", "session_id", "judgment_id"],
    "properties": {
        "repeat_group": {"type": "string"},
        "session_id": {"type": "string"},
        "judgment_id": {"type": "string"},
    },
}

ANNOTATION_SCHEMAS = {
    "absolute": ABSOLUTE_ANNOTATION_SCHEMA,
    "pairwise": PAIRWISE_ANNOTATION_SCHEMA,
    "segment": SEGMENT_ANNOTATION_SCHEMA,
    "annotator": ANNOTATOR_SCHEMA,
    "blind_repeat": BLIND_REPEAT_SCHEMA,
}

