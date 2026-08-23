"""Read osu!stable's local beatmap database for an empirical NM star scale.

The parser intentionally extracts only fields required to advance safely to
the next record plus the osu!standard NoMod star value.  It is not a general
purpose ``osu!.db`` model.
"""

from __future__ import annotations

import hashlib
import io
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


def _skip_star_pairs(fh: BinaryIO, *, capture_nm: bool) -> float | None:
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
    return nm


def _skip_timing_points(fh: BinaryIO) -> None:
    count = _unpack(fh, "i")
    _read_exact(fh, count * 17)  # double BPM + double offset + bool inherited


def _read_record(
    fh: BinaryIO, version: int
) -> tuple[str | None, str | None, float | None]:
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
    if version < 20140609:
        _read_exact(fh, 4 * 4)  # legacy per-ruleset star singles
    else:
        for mode in range(4):
            candidate = _skip_star_pairs(fh, capture_nm=(mode == 0))
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
