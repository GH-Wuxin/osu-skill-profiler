"""Deterministic mod parsing and normalization for Map Demand.

This module owns representation only.  It does not apply difficulty, timing,
visibility, or ruleset transforms to beatmap signals.  A normalized context
therefore distinguishes a valid mod specification from one the current
MapDemand implementation can actually score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

MOD_CONTEXT_VERSION = "0.1.0"
MOD_CONTEXT_SCHEMA_VERSION = "mod_context_v0.1.0"

# Stable order used in serialized contexts and cache identities.  This follows
# the familiar legacy acronym order where practical; the exact order is part
# of MOD_CONTEXT_SCHEMA_VERSION, not a claim about gameplay precedence.
MOD_ORDER: tuple[str, ...] = (
    "NF",
    "EZ",
    "HD",
    "HR",
    "SD",
    "DT",
    "RX",
    "HT",
    "NC",
    "FL",
    "AT",
    "SO",
    "AP",
    "PF",
    "DC",
    "DA",
    "WU",
    "WD",
    "AS",
    "TP",
)
_ORDER_INDEX = {mod: index for index, mod in enumerate(MOD_ORDER)}
_KNOWN_MODS = frozenset(MOD_ORDER)

_ALIASES = {
    "NM": "NM",
    "NOMOD": "NM",
    "NONE": "NM",
    "NF": "NF",
    "NOFAIL": "NF",
    "EZ": "EZ",
    "EASY": "EZ",
    "HD": "HD",
    "HIDDEN": "HD",
    "HR": "HR",
    "HARDROCK": "HR",
    "SD": "SD",
    "SUDDENDEATH": "SD",
    "DT": "DT",
    "DOUBLETIME": "DT",
    "RX": "RX",
    "RELAX": "RX",
    "HT": "HT",
    "HALFTIME": "HT",
    "NC": "NC",
    "NIGHTCORE": "NC",
    "FL": "FL",
    "FLASHLIGHT": "FL",
    "AT": "AT",
    "AUTOPLAY": "AT",
    "SO": "SO",
    "SPUNOUT": "SO",
    "AP": "AP",
    "AUTOPILOT": "AP",
    "PF": "PF",
    "PERFECT": "PF",
    "DC": "DC",
    "DAYCORE": "DC",
    "DA": "DA",
    "DIFFICULTYADJUST": "DA",
    "WU": "WU",
    "WINDUP": "WU",
    "WD": "WD",
    "WINDDOWN": "WD",
    "AS": "AS",
    "ADAPTIVESPEED": "AS",
    "TP": "TP",
    "TARGETPRACTICE": "TP",
}

_NEUTRAL_FOR_MAP_DEMAND = frozenset({"NF", "SD", "PF"})
_TRANSFORM_PENDING = frozenset({"EZ", "HR", "HT", "DC", "DT", "NC"})
_SIGNAL_REQUIRED = frozenset({"HD"})
_SIGNAL_PENDING = frozenset()
_DEFERRED_SEPARATE_DIMENSION = frozenset({"FL"})
_MECHANICS_UNSUPPORTED = frozenset({"RX", "AT", "SO", "AP", "DA", "WU", "WD", "AS", "TP"})

_SPLIT_RE = re.compile(r"[\s,+|/]+")


def _sort_mods(mods: Iterable[str]) -> list[str]:
    unique = {str(mod).upper() for mod in mods}
    return sorted(unique, key=lambda mod: (_ORDER_INDEX.get(mod, len(MOD_ORDER)), mod))


def canonicalize_effective_mods(mods: Iterable[str]) -> list[str]:
    """Return a deterministic, uppercase, duplicate-free identity list."""
    return _sort_mods(mods)


def _alias_key(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value).upper()


def _parse_piece(piece: str) -> list[str] | None:
    key = _alias_key(piece)
    if not key:
        return []
    alias = _ALIASES.get(key)
    if alias is not None:
        return [alias]

    # Legacy compact forms such as HDDT and HRDT are unambiguous because all
    # acronyms in this contract are exactly two characters.
    if len(key) % 2 == 0:
        chunks = [key[index : index + 2] for index in range(0, len(key), 2)]
        if all(chunk in _KNOWN_MODS or chunk == "NM" for chunk in chunks):
            return chunks
    return None


def _tokenize(requested_mods: Iterable[str] | str | None) -> tuple[list[str], list[str]]:
    if requested_mods is None:
        return [], []
    values: Iterable[Any]
    if isinstance(requested_mods, str):
        values = [requested_mods]
    else:
        try:
            values = list(requested_mods)
        except TypeError:
            return [], [repr(requested_mods)]

    parsed: list[str] = []
    unknown: list[str] = []
    for value in values:
        if not isinstance(value, str):
            unknown.append(repr(value))
            continue
        raw = value.strip()
        if not raw:
            continue

        whole = _parse_piece(raw)
        if whole is not None:
            parsed.extend(whole)
            continue

        pieces = [piece for piece in _SPLIT_RE.split(raw) if piece]
        if len(pieces) <= 1:
            unknown.append(raw.upper())
            continue
        for piece in pieces:
            result = _parse_piece(piece)
            if result is None:
                unknown.append(piece.upper())
            else:
                parsed.extend(result)
    return parsed, sorted(set(unknown))


def _invalid_context(
    *, requested: list[str], unknown: list[str], code: str, message: str, conflicts: list[list[str]]
) -> dict[str, Any]:
    return {
        "schema_version": MOD_CONTEXT_SCHEMA_VERSION,
        "status": "INVALID",
        "analysis_support": "INVALID",
        "requested_mods": requested,
        "effective_mods": [],
        "clock_rate": 1.0,
        "alias_folds": [],
        "neutral_mods": [],
        "pending_transforms": [],
        "required_signals": [],
        "pending_signals": [],
        "deferred_mods": [],
        "unsupported_mechanics": [],
        "conflicts": conflicts,
        "unknown_mods": unknown,
        "errors": [{"code": code, "message": message}],
    }


def normalize_mods(requested_mods: Iterable[str] | str | None = ()) -> dict[str, Any]:
    """Parse and normalize a mod specification without applying transforms.

    NC and DC retain their requested identity but fold to DT and HT in
    ``effective_mods`` because their default map-demand timing behaviour is
    identical.  Explicit incompatible pairs still fail closed.
    """
    parsed, unknown = _tokenize(requested_mods)
    requested = _sort_mods(parsed)
    if unknown:
        return _invalid_context(
            requested=requested,
            unknown=unknown,
            code="UNKNOWN_MOD",
            message="one or more mod tokens are not recognized by MOD_CONTEXT_V01",
            conflicts=[],
        )

    requested_set = set(requested)
    conflicts: list[list[str]] = []
    if "NM" in requested_set and len(requested_set) > 1:
        conflicts.append(["NM", *_sort_mods(requested_set - {"NM"})])
    if {"EZ", "HR"}.issubset(requested_set):
        conflicts.append(["EZ", "HR"])
    if {"SD", "PF"}.issubset(requested_set):
        conflicts.append(["SD", "PF"])

    rate_mods = requested_set.intersection({"DT", "NC", "HT", "DC", "WU", "WD", "AS"})
    if len(rate_mods) > 1:
        conflicts.append(_sort_mods(rate_mods))

    if conflicts:
        conflicts = sorted(conflicts, key=lambda pair: tuple(pair))
        return _invalid_context(
            requested=requested,
            unknown=[],
            code="MOD_CONFLICT",
            message="requested mods contain an incompatible combination",
            conflicts=conflicts,
        )

    # NM is an explicit spelling of the empty effective state.
    requested_without_nm = requested_set - {"NM"}
    folds: list[dict[str, str]] = []
    effective_set = set(requested_without_nm - _NEUTRAL_FOR_MAP_DEMAND)
    if "NC" in effective_set:
        effective_set.remove("NC")
        effective_set.add("DT")
        folds.append({"from": "NC", "to": "DT"})
    if "DC" in effective_set:
        effective_set.remove("DC")
        effective_set.add("HT")
        folds.append({"from": "DC", "to": "HT"})

    clock_rate = 1.0
    if requested_set.intersection({"DT", "NC"}):
        clock_rate = 1.5
    elif requested_set.intersection({"HT", "DC"}):
        clock_rate = 0.75

    neutral = _sort_mods(requested_set.intersection(_NEUTRAL_FOR_MAP_DEMAND))
    pending_transforms = _sort_mods(requested_set.intersection(_TRANSFORM_PENDING))
    required_signals = _sort_mods(requested_set.intersection(_SIGNAL_REQUIRED))
    pending_signals = _sort_mods(requested_set.intersection(_SIGNAL_PENDING))
    deferred = _sort_mods(requested_set.intersection(_DEFERRED_SEPARATE_DIMENSION))
    unsupported = _sort_mods(requested_set.intersection(_MECHANICS_UNSUPPORTED))
    transform_required = bool(pending_transforms or required_signals) and not (
        pending_signals or deferred or unsupported
    )
    analysis_support = (
        "NOT_IMPLEMENTED"
        if pending_signals or deferred or unsupported
        else ("TRANSFORM_REQUIRED" if transform_required else "SUPPORTED")
    )

    return {
        "schema_version": MOD_CONTEXT_SCHEMA_VERSION,
        "status": "NORMALIZED",
        "analysis_support": analysis_support,
        "requested_mods": requested,
        "effective_mods": _sort_mods(effective_set),
        "clock_rate": clock_rate,
        "alias_folds": folds,
        "neutral_mods": neutral,
        "pending_transforms": pending_transforms,
        "required_signals": required_signals,
        "pending_signals": pending_signals,
        "deferred_mods": deferred,
        "unsupported_mechanics": unsupported,
        "conflicts": [],
        "unknown_mods": [],
        "errors": [],
    }
