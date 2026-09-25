"""Read osu!stable's local beatmap database for an empirical NM star scale.

The parser intentionally extracts only fields required to advance safely to
the next record plus the osu!standard NoMod star value.  It is not a general
purpose ``osu!.db`` model.
"""

from __future__ import annotations

import hashlib
import io
import math
import struct
from pathlib import Path
from typing import BinaryIO, Any


class OsuDbFormatError(ValueError):
    pass


def _read_exact(fh: BinaryIO, size: int) -> bytes:
    value = fh.read(size)
    if len(value) != size:
        raise OsuDbFormatError(f"unexpected EOF: wanted {size} bytes, got {len(value)}")
    return value


def _unpack(fh: BinaryIO, fmt: str) -> Any:
    return struct.unpack("<" + fmt, _read_exact(fh, struct.calcsize(fmt)))[0]


def _uleb128(fh: BinaryIO) -> int:
    value = 0
    shift = 0
    for _ in range(10):
        byte = _unpack(fh, "B")
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
    raise OsuDbFormatError("ULEB128 value is too long")


def _string(fh: BinaryIO) -> str | None:
    marker = _unpack(fh, "B")
    if marker == 0x00:
        return None
    if marker != 0x0B:
        raise OsuDbFormatError(f"invalid string marker 0x{marker:02x}")
    return _read_exact(fh, _uleb128(fh)).decode("utf-8", errors="replace")


def _skip_star_pairs(
    fh: BinaryIO,
    *,
    capture_nm: bool,
    stars_by_mod: dict[int, float] | None = None,
) -> float | None:
    count = _unpack(fh, "i")
    nm: float | None = None
    for _ in range(count):
        int_marker = _unpack(fh, "B")
        mods = _unpack(fh, "i")
        double_marker = _unpack(fh, "B")
        if double_marker == 0x0C:
            stars = _unpack(fh, "f")
        elif double_marker == 0x0D:
            stars = _unpack(fh, "d")
        else:
            stars = float("nan")
        # Current stable stores a Single (0x0c); older documented databases
        # store a Double (0x0d).
        if int_marker != 0x08 or double_marker not in (0x0C, 0x0D):
            raise OsuDbFormatError(
                f"invalid IntDoublePair markers 0x{int_marker:02x}/0x{double_marker:02x}"
            )
        if capture_nm and mods == 0:
            nm = float(stars)
        if stars_by_mod is not None and math.isfinite(float(stars)):
            stars_by_mod[int(mods)] = float(stars)
    return nm


def _skip_timing_points(fh: BinaryIO) -> None:
    count = _unpack(fh, "i")
    _read_exact(fh, count * 17)  # double BPM + double offset + bool inherited


def _read_record(
    fh: BinaryIO,
    version: int,
    *,
    capture_mods: bool = False,
) -> tuple[str | None, str | None, float | None] | tuple[str | None, str | None, float | None, dict[int, float]]:
    # Text metadata through beatmap filename.
    for _ in range(7):
        _string(fh)
    md5 = _string(fh)
    filename = _string(fh)

    _read_exact(fh, 1 + 2 * 3 + 8)  # ranked, object counts, last modified
    if version < 20140609:
        _read_exact(fh, 4)  # legacy AR/CS/HP/OD bytes
    else:
        _read_exact(fh, 4 * 4)  # AR/CS/HP/OD singles
    _read_exact(fh, 8)  # slider velocity

    nm_stars: float | None = None
    stars_by_mod: dict[int, float] | None = {} if capture_mods else None
    if version < 20140609:
        _read_exact(fh, 4 * 4)  # legacy per-ruleset star singles
    else:
        for mode in range(4):
            candidate = _skip_star_pairs(
                fh,
                capture_nm=(mode == 0),
                # The osu!.db record stores four rulesets in sequence.  The
                # universal profiler is osu!standard-only, so capture mod
                # anchors from mode 0 and still consume the other rulesets.
                stars_by_mod=stars_by_mod if mode == 0 else None,
            )
            if candidate is not None:
                nm_stars = candidate

    _read_exact(fh, 4 * 3)  # drain, total, preview
    _skip_timing_points(fh)
    _read_exact(fh, 4 * 3 + 1 * 4 + 2 + 4 + 1)  # ids, grades, offset, stack, mode
    _string(fh)  # source
    _string(fh)  # tags
    _read_exact(fh, 2)
    _string(fh)  # title font
    _read_exact(fh, 1 + 8 + 1)
    folder = _string(fh)
    _read_exact(fh, 8 + 1 * 5)
    if version < 20140609:
        _read_exact(fh, 2)
    _read_exact(fh, 4 + 1)
    relative_path = None
    if folder and filename:
        relative_path = f"{folder}/{filename}"
    if capture_mods:
        return md5, relative_path, nm_stars, stars_by_mod or {}
    return md5, relative_path, nm_stars


def read_nm_star_distribution(path: str | Path) -> dict[str, Any]:
    db_path = Path(path).resolve()
    digest = hashlib.sha256()
    with db_path.open("rb") as raw:
        data = raw.read()
    digest.update(data)
    fh = io.BytesIO(data)
    version = _unpack(fh, "i")
    folder_count = _unpack(fh, "i")
    account_unlocked = bool(_unpack(fh, "B"))
    _unpack(fh, "q")
    player_name = _string(fh)
    beatmap_count = _unpack(fh, "i")

    stars: list[float] = []
    md5_to_nm_stars: dict[str, float] = {}
    relative_path_to_nm_stars: dict[str, float] = {}
    for index in range(beatmap_count):
        try:
            md5, relative_path, nm = _read_record(fh, version)
        except (UnicodeDecodeError, struct.error, OsuDbFormatError) as exc:
            raise OsuDbFormatError(f"beatmap record {index}: {exc}") from exc
        if nm is None or not (0.0 <= nm < float("inf")):
            continue
        stars.append(nm)
        if md5:
            md5_to_nm_stars[md5.lower()] = nm
        if relative_path:
            relative_path_to_nm_stars[relative_path.replace("\\", "/").casefold()] = nm

    stars.sort()
    return {
        "database_version": version,
        "folder_count": folder_count,
        "account_unlocked": account_unlocked,
        "player_name": player_name,
        "beatmap_count": beatmap_count,
        "nm_star_count": len(stars),
        "nm_stars": stars,
        "md5_to_nm_stars": md5_to_nm_stars,
        "relative_path_to_nm_stars": relative_path_to_nm_stars,
        "database_sha256": digest.hexdigest(),
        "bytes_consumed": fh.tell(),
        "database_bytes": len(data),
    }


# Stable osu!standard mod bits used by osu!.db.  The index intentionally keeps
# every stored context except any context containing FL; FL is a separate
# visual-difficulty dimension and is outside the current map-demand contract.
MOD_BITS: dict[str, int] = {
    "NF": 1,
    "EZ": 2,
    "TD": 4,
    "HD": 8,
    "HR": 16,
    "SD": 32,
    "DT": 64,
    "RX": 128,
    "HT": 256,
    "NC": 512,
    "FL": 1024,
    "AT": 2048,
    "SO": 4096,
    "AP": 8192,
    "PF": 16384,
    "4K": 32768,
    "5K": 65536,
    "6K": 131072,
    "7K": 262144,
    "8K": 524288,
    "FI": 1048576,
    "RD": 2097152,
    "CN": 4194304,
    "TP": 8388608,
    "9K": 16777216,
    "CO": 33554432,
    "1K": 67108864,
    "2K": 134217728,
    "3K": 268435456,
}
_BIT_TO_MOD = {value: key for key, value in MOD_BITS.items()}


def mod_bitmask_to_label(bitmask: int) -> str:
    """Return a stable compact context label for an osu!.db mod bitmask."""

    value = int(bitmask)
    if value == 0:
        return "NM"
    labels = [name for bit, name in sorted(_BIT_TO_MOD.items()) if value & bit]
    return "".join(labels) if labels else f"BITS{value}"


def read_standard_star_index(path: str | Path, *, exclude_flashlight: bool = True) -> dict[str, Any]:
    """Read ppy star anchors for every stored mod context.

    The existing ``read_nm_star_distribution`` remains the cheap backwards
    compatible NM-only API.  This opt-in reader is used by the universal map
    index and preserves per-context values instead of collapsing them to NM.
    """

    db_path = Path(path).resolve()
    raw = db_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    fh = io.BytesIO(raw)
    version = _unpack(fh, "i")
    folder_count = _unpack(fh, "i")
    account_unlocked = bool(_unpack(fh, "B"))
    _unpack(fh, "q")
    player_name = _string(fh)
    beatmap_count = _unpack(fh, "i")
    stars_by_mod: dict[str, list[float]] = {}
    md5_to_stars: dict[str, dict[str, float]] = {}
    path_to_stars: dict[str, dict[str, float]] = {}
    for index in range(beatmap_count):
        try:
            md5, relative_path, _nm, record_stars = _read_record(
                fh, version, capture_mods=True
            )
        except (UnicodeDecodeError, struct.error, OsuDbFormatError) as exc:
            raise OsuDbFormatError(f"beatmap record {index}: {exc}") from exc
        filtered: dict[str, float] = {}
        for bitmask, star in record_stars.items():
            if exclude_flashlight and bitmask & MOD_BITS["FL"]:
                continue
            if not math.isfinite(star) or star < 0.0:
                continue
            context = mod_bitmask_to_label(bitmask)
            filtered[context] = float(star)
            stars_by_mod.setdefault(context, []).append(float(star))
        if md5:
            md5_to_stars[md5.lower()] = filtered
        if relative_path:
            path_to_stars[relative_path.replace("\\", "/").casefold()] = filtered
    for values in stars_by_mod.values():
        values.sort()
    return {
        "database_version": version,
        "folder_count": folder_count,
        "account_unlocked": account_unlocked,
        "player_name": player_name,
        "beatmap_count": beatmap_count,
        "stars_by_mod": stars_by_mod,
        "md5_to_stars_by_mod": md5_to_stars,
        "relative_path_to_stars_by_mod": path_to_stars,
        "excluded_mods": ["FL"] if exclude_flashlight else [],
        "database_sha256": digest,
        "bytes_consumed": fh.tell(),
        "database_bytes": len(raw),
    }


__all__ = [
    "MOD_BITS",
    "OsuDbFormatError",
    "mod_bitmask_to_label",
    "read_nm_star_distribution",
    "read_standard_star_index",
]
