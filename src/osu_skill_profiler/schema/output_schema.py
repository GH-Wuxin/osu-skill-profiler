"""Public output JSON Schema for skill profiles."""

from __future__ import annotations

from .. import SCHEMA_VERSION

BEATMAP_SCHEMA = {
    "type": "object",
    "required": ["beatmap_id", "beatmapset_id", "mapper", "difficulty_name", "source", "difficulty"],
    "properties": {
        "beatmap_id": {"type": ["integer", "null"]},
        "beatmapset_id": {"type": ["integer", "null"]},
        "mapper": {"type": "string"},
        "difficulty_name": {"type": "string"},
        "source": {"type": "string"},
        "difficulty": {
            "type": "object",
            "properties": {
                "AR": {"type": ["number", "null"]},
                "OD": {"type": ["number", "null"]},
                "CS": {"type": ["number", "null"]},
                "HP": {"type": ["number", "null"]},
                "SliderMultiplier": {"type": ["number", "null"]},
                "SliderTickRate": {"type": ["number", "null"]},
            },
        },
    },
}

SKILL_SCHEMA = {
    "type": "object",
    "required": ["score", "confidence", "status"],
    "properties": {
        "score": {"type": ["number", "null"]},
        "confidence": {"type": ["number", "null"]},
        "status": {"enum": ["not_inferred", "inferred", "weak_candidate"]},
    },
}

SEGMENT_SCHEMA = {
    "type": "object",
    "required": ["start_ms", "end_ms", "start_idx", "end_idx", "features"],
    "properties": {
        "start_ms": {"type": "number"},
        "end_ms": {"type": "number"},
        "start_idx": {"type": "integer", "minimum": 0},
        "end_idx": {"type": "integer", "minimum": 0},
        "features": {"type": "object"},
    },
}

SLIDER_EVIDENCE_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version",
        "status",
        "geometry",
        "judgement_contract",
        "semantic_routes",
        "formal_axis_admission",
        "slider_pressure_scalar_admitted",
        "player_skill_score_admitted",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "status": {"type": "string"},
        "geometry": {"type": "object"},
        "pressure_vector": {"type": ["object", "null"]},
        "replay_observation": {"type": "object"},
        "score_observation": {"type": "object"},
        "judgement_contract": {"type": "object"},
        "semantic_routes": {"type": "object"},
        "formal_axis_admission": {"type": "string"},
        "slider_pressure_scalar_admitted": {"type": "boolean"},
        "player_skill_score_admitted": {"type": "boolean"},
        "provenance": {"type": "array", "items": {"type": "string"}},
    },
}

WEAK_LABEL_SCHEMA = {
    "type": "object",
    "required": [
        "rule_id",
        "skill",
        "suggested_score",
        "confidence",
        "evidence",
        "segment_index",
        "features_version",
        "taxonomy_version",
        "input_checksum",
        "disclaimer",
    ],
    "properties": {
        "rule_id": {"type": "string"},
        "skill": {"type": "string"},
        "suggested_score": {"type": ["number", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "segment_index": {"type": ["integer", "null"]},
        "features_version": {"type": "string"},
        "taxonomy_version": {"type": "string"},
        "input_checksum": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "disclaimer": {"type": "string"},
    },
}

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "schema_version",
        "taxonomy_version",
        "model_version",
        "model_kind",
        "status",
        "beatmap",
        "features",
        "map_demand",
        "skills",
        "segments",
        "weak_labels",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "taxonomy_version": {"type": "string"},
        "model_version": {"type": "string"},
        "model_kind": {"enum": ["baseline", "heuristic", "ml", "unknown"]},
        "status": {"enum": ["ok", "not_inferred"]},
        "disclaimer": {"type": "string"},
        "beatmap": BEATMAP_SCHEMA,
        "features": {"type": "object"},
        "map_demand": {"type": "object"},
        "slider_evidence": SLIDER_EVIDENCE_SCHEMA,
        "skills": {
            "type": "object",
            "additionalProperties": SKILL_SCHEMA,
        },
        "segments": {"type": "array", "items": SEGMENT_SCHEMA},
        "weak_labels": {"type": "array", "items": WEAK_LABEL_SCHEMA},
    },
}
