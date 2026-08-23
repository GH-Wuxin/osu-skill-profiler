"""Human-presentation contracts and eligibility checks for pilot v0.2.

This module is deliberately downstream of the verified Feature, Local and
Weak Evidence contracts.  It decides whether an existing entity can be shown
to a human with the local browser renderer; it does not reinterpret the
underlying signal or decide an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import struct
from typing import Any, Callable, Mapping

from osu_skill_profiler.parser.normalized import normalize
from osu_skill_profiler.parser.osu_parser import parse_osu_file
from osu_skill_profiler.signals.extractor import LocalSignalExtractor
from osu_skill_profiler.signals.path import build_slider_path


PRESENTATION_ELIGIBILITY_VERSION = "0.2.0"
HUMAN_PROPOSITION_CONTRACT_VERSION = "0.2.0"

# Operational browser-presentation limits, not canonical osu! validity rules.
# In the 153-map v0.1 source batch, the longest non-Aspire timeline is about
# 35.9 minutes while the reported Aspire case expands to about 119.8 minutes;
# 45 minutes retains every observed non-Aspire source.  The non-Aspire maxima
# for BPM and SV are 780 and 50, so the ceilings below retain those margins.
MAX_INTERACTIVE_TIMELINE_MS = 45 * 60 * 1000.0
MAX_PRESENTATION_BPM = 1000.0
MAX_PRESENTATION_SV = 100.0
AUDIO_COVERAGE_TOLERANCE_MS = 1500.0


class EmptyDomainPolicy(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PAIR_INELIGIBLE = "PAIR_INELIGIBLE"


class HumanJudgeability(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_YET_HUMAN_JUDGEABLE = "NOT_YET_HUMAN_JUDGEABLE"


class PresentationReason(str, Enum):
    MAP_ASSET_UNAVAILABLE = "MAP_ASSET_UNAVAILABLE"
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
    CANONICAL_SEGMENT_UNRESOLVED = "CANONICAL_SEGMENT_UNRESOLVED"
    AUDIO_UNAVAILABLE = "AUDIO_UNAVAILABLE"
    AUDIO_DURATION_UNAVAILABLE = "AUDIO_DURATION_UNAVAILABLE"
    AUDIO_WINDOW_UNCOVERED = "AUDIO_WINDOW_UNCOVERED"
    INVALID_PRESENTATION_WINDOW = "INVALID_PRESENTATION_WINDOW"
    TIMELINE_TOO_LONG = "TIMELINE_TOO_LONG"
    TIMING_NONFINITE = "TIMING_NONFINITE"
    BPM_PRESENTATION_UNSAFE = "BPM_PRESENTATION_UNSAFE"
    SV_PRESENTATION_UNSAFE = "SV_PRESENTATION_UNSAFE"
    OBJECT_OUTSIDE_RENDERER = "OBJECT_OUTSIDE_RENDERER"
    OBJECT_TIME_UNREPRESENTABLE = "OBJECT_TIME_UNREPRESENTABLE"
    SLIDER_GEOMETRY_UNRENDERABLE = "SLIDER_GEOMETRY_UNRENDERABLE"
    SLIDER_TRAVERSAL_UNREPRESENTABLE = "SLIDER_TRAVERSAL_UNREPRESENTABLE"
    EMPTY_PROPOSITION_DOMAIN = "EMPTY_PROPOSITION_DOMAIN"
    PROPOSITION_NOT_HUMAN_JUDGEABLE = "PROPOSITION_NOT_HUMAN_JUDGEABLE"


@dataclass(frozen=True)
class HumanPropositionContract:
    proposition_id: str
    proposition_version: str
    machine_semantics: str
    human_question: str
    attend_to: str
    not_asking: tuple[str, ...]
    valid_scope: str
    empty_domain_policy: EmptyDomainPolicy
    presentation_requirements: tuple[str, ...]
    cannot_judge_when: tuple[str, ...]
    known_ambiguity: tuple[str, ...]
    judgeability: HumanJudgeability = HumanJudgeability.ELIGIBLE

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": HUMAN_PROPOSITION_CONTRACT_VERSION,
            "proposition_id": self.proposition_id,
            "proposition_version": self.proposition_version,
            "machine_semantics": self.machine_semantics,
            "human_question": self.human_question,
            "attend_to": self.attend_to,
            "not_asking": list(self.not_asking),
            "valid_scope": self.valid_scope,
            "empty_domain_policy": self.empty_domain_policy.value,
            "presentation_requirements": list(self.presentation_requirements),
            "cannot_judge_when": list(self.cannot_judge_when),
            "known_ambiguity": list(self.known_ambiguity),
            "judgeability": self.judgeability.value,
        }


HUMAN_PROPOSITIONS: dict[str, HumanPropositionContract] = {
    "ws01.provisional.movement_demand_high": HumanPropositionContract(
        proposition_id="ws01.provisional.movement_demand_high",
        proposition_version="0.1.0",
        machine_semantics=(
            "Map-level high-tail movement evidence from p95 normalised spacing and velocity, "
            "with an independent ppy snap-tail view; it is not a canonical skill scalar."
        ),
        human_question="哪一侧整张谱面的光标移动通常更快、跨度也更大？",
        attend_to="观察需要快速跨越较大间距的移动段落，以及这种段落是否持续出现。",
        not_asking=("不是比较物件总数", "不是只找全图最远的一跳", "不是比较综合难度"),
        valid_scope="MAP_PAIR",
        empty_domain_policy=EmptyDomainPolicy.NOT_APPLICABLE,
        presentation_requirements=("完整可播放时间轴", "可渲染的物件位置", "显式 NM 与 CS"),
        cannot_judge_when=("音画不同步", "谱面无法正常播放", "移动差异无法可靠辨认"),
        known_ambiguity=("速度和跨度可能指向不同侧",),
    ),
    "ws01.provisional.dense_timing_pressure_high": HumanPropositionContract(
        proposition_id="ws01.provisional.dense_timing_pressure_high",
        proposition_version="0.1.0",
        machine_semantics=(
            "Map-level conjunction of peak one-second object rate and sustained runs of "
            "successive object gaps no greater than 125 ms."
        ),
        human_question="哪一侧更常出现需要连续快速点击的密集段落？",
        attend_to="观察高密度物件是否连续形成快速点击段，而不只看某个孤立瞬间。",
        not_asking=("不是比较歌曲 BPM", "不是比较物件总数", "不是判断串的具体指法"),
        valid_scope="MAP_PAIR",
        empty_domain_policy=EmptyDomainPolicy.NOT_APPLICABLE,
        presentation_requirements=("完整可播放时间轴", "音画同步", "所有相关物件可渲染"),
        cannot_judge_when=("时间轴或音频异常", "密集段落不可正常播放", "两侧差异无法可靠辨认"),
        known_ambiguity=("短促峰值与较长但稍慢的密集段可能难以排序",),
    ),
    "ws01.provisional.slider_tracking_travel_high": HumanPropositionContract(
        proposition_id="ws01.provisional.slider_tracking_travel_high",
        proposition_version="0.1.0",
        machine_semantics=(
            "Canonical five-second segment p90 of corrected CS-normalised Local lazy slider "
            "follow distance across object rows; non-slider rows are zero in the machine signal."
        ),
        human_question="哪一侧片段中较长的一批滑条，通常需要更远的持续跟随？",
        attend_to="比较片段里较长一档滑条的跟随距离，结合滑条路径和重复折返观察。",
        not_asking=("不是把所有滑条距离相加", "不是只比较最长的一根", "不是比较滑条数量"),
        valid_scope="SEGMENT_PAIR",
        empty_domain_policy=EmptyDomainPolicy.PAIR_INELIGIBLE,
        presentation_requirements=("两侧目标片段都至少有一根可渲染滑条", "滑条球可按真实重复方向移动", "音画同步"),
        cannot_judge_when=("滑条路径或球移动无法看清", "有效滑条太少而无法判断‘通常’", "两侧差异无法可靠辨认"),
        known_ambiguity=("机器 p90 仍可能受片段物件构成影响；本轮只测试其人类可判定性",),
    ),
    "ws01.provisional.slider_control_load_high": HumanPropositionContract(
        proposition_id="ws01.provisional.slider_control_load_high",
        proposition_version="0.1.0",
        machine_semantics="Map-level conjunction over slider ratio, duration p90 and repeat count.",
        human_question="",
        attend_to="",
        not_asking=(),
        valid_scope="MAP_PAIR",
        empty_domain_policy=EmptyDomainPolicy.PAIR_INELIGIBLE,
        presentation_requirements=(),
        cannot_judge_when=(),
        known_ambiguity=("当前组合语义不能稳定翻译为单一人类判断",),
        judgeability=HumanJudgeability.NOT_YET_HUMAN_JUDGEABLE,
    ),
}


def _mp3_duration_ms(path: Path) -> float | None:
    """Read MPEG duration from a bounded header scan.

    Xing/VBRI frame counts are preferred.  Otherwise the first valid frame's
    bitrate supplies a conservative CBR estimate.  This is a presentation
    preflight, not an audio decoder.
    """

    size = path.stat().st_size
    with path.open("rb") as handle:
        prefix = handle.read(min(size, 256 * 1024))
    offset = 0
    if prefix.startswith(b"ID3") and len(prefix) >= 10:
        tag = prefix[6:10]
        offset = 10 + ((tag[0] & 0x7f) << 21) + ((tag[1] & 0x7f) << 14) + ((tag[2] & 0x7f) << 7) + (tag[3] & 0x7f)
    bitrates = {
        (1, 1): (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
        (1, 2): (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),
        (1, 3): (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
        (2, 1): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
        (2, 2): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
        (2, 3): (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    }
    rates = {1: (44100, 48000, 32000), 2: (22050, 24000, 16000), 25: (11025, 12000, 8000)}
    for pos in range(offset, max(offset, len(prefix) - 4)):
        header = int.from_bytes(prefix[pos:pos + 4], "big")
        if header & 0xffe00000 != 0xffe00000:
            continue
        version_bits = (header >> 19) & 3
        layer_bits = (header >> 17) & 3
        bitrate_index = (header >> 12) & 15
        rate_index = (header >> 10) & 3
        if version_bits == 1 or layer_bits == 0 or bitrate_index in (0, 15) or rate_index == 3:
            continue
        version = 1 if version_bits == 3 else 2 if version_bits == 2 else 25
        layer = 4 - layer_bits
        table_version = 1 if version == 1 else 2
        bitrate = bitrates.get((table_version, layer), ())[bitrate_index] * 1000
        sample_rate = rates[version][rate_index]
        samples_per_frame = 384 if layer == 1 else 1152 if layer == 2 or version == 1 else 576
        channel_mode = (header >> 6) & 3
        side_info = 17 if channel_mode == 3 else 32
        if version != 1:
            side_info = 9 if channel_mode == 3 else 17
        xing = pos + 4 + side_info
        if prefix[xing:xing + 4] in (b"Xing", b"Info") and len(prefix) >= xing + 12:
            flags = int.from_bytes(prefix[xing + 4:xing + 8], "big")
            if flags & 1:
                frames = int.from_bytes(prefix[xing + 8:xing + 12], "big")
                duration = frames * samples_per_frame / sample_rate * 1000.0
                return duration if math.isfinite(duration) and duration > 0 else None
        vbri = pos + 36
        if prefix[vbri:vbri + 4] == b"VBRI" and len(prefix) >= vbri + 18:
            frames = int.from_bytes(prefix[vbri + 14:vbri + 18], "big")
            duration = frames * samples_per_frame / sample_rate * 1000.0
            return duration if math.isfinite(duration) and duration > 0 else None
        duration = (size - pos) * 8 / bitrate * 1000.0
        return duration if math.isfinite(duration) and duration > 0 else None
    return None


def _ogg_duration_ms(path: Path) -> float | None:
    with path.open("rb") as handle:
        prefix = handle.read(128 * 1024)
        handle.seek(max(0, path.stat().st_size - 128 * 1024))
        suffix = handle.read()
    marker = prefix.find(b"\x01vorbis")
    if marker < 0 or len(prefix) < marker + 16:
        return None
    sample_rate = struct.unpack_from("<I", prefix, marker + 12)[0]
    if sample_rate <= 0:
        return None
    last = suffix.rfind(b"OggS")
    if last < 0 or len(suffix) < last + 14:
        return None
    granule = struct.unpack_from("<Q", suffix, last + 6)[0]
    duration = granule / sample_rate * 1000.0
    return duration if math.isfinite(duration) and duration > 0 else None


def audio_duration_ms(path: Path) -> float | None:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return _mp3_duration_ms(path)
    if suffix in (".ogg", ".oga"):
        return _ogg_duration_ms(path)
    if suffix == ".wav":
        with path.open("rb") as handle:
            data = handle.read(64 * 1024)
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None
        pos = 12
        byte_rate = data_size = None
        while pos + 8 <= len(data):
            kind, length = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
            body = pos + 8
            if kind == b"fmt " and length >= 16 and body + 12 <= len(data):
                byte_rate = struct.unpack_from("<I", data, body + 8)[0]
            if kind == b"data":
                data_size = length
                break
            pos = body + length + (length & 1)
        if byte_rate and data_size is not None:
            return data_size / byte_rate * 1000.0
    return None


class HumanPresentationEligibility:
    """Mechanically validate real browser presentation for existing entities."""

    def __init__(
        self,
        resolver: Any,
        *,
        duration_probe: Callable[[Path], float | None] = audio_duration_ms,
    ) -> None:
        self.resolver = resolver
        self.duration_probe = duration_probe
        self._map_cache: dict[str, tuple[Any, Any, float | None]] = {}

    def _map(self, checksum: str) -> tuple[Any, Any, float | None]:
        cached = self._map_cache.get(checksum)
        if cached is not None:
            return cached
        resolved = self.resolver.resolve_map(checksum)
        beatmap = parse_osu_file(resolved.osu_path)
        duration = self.duration_probe(resolved.audio_path) if resolved.audio_path else None
        cached = (resolved, beatmap, duration)
        self._map_cache[checksum] = cached
        return cached

    @staticmethod
    def _window(ref: Mapping[str, Any], normalized: Any) -> tuple[float, float]:
        if ref["scope"] == "SEGMENT":
            return max(0.0, float(ref["segment_start_ms"]) - 2000.0), float(ref["segment_end_ms"]) + 1500.0
        return min(float(row.raw.time_ms) for row in normalized.objects), max(float(row.canonical_end_time_ms()) for row in normalized.objects)

    def evaluate_entity(
        self,
        entity: Mapping[str, Any],
        proposition_id: str,
    ) -> dict[str, Any]:
        ref = entity["entity"]
        checksum = str(ref["map_checksum"])
        reasons: list[str] = []
        contract = HUMAN_PROPOSITIONS.get(proposition_id)
        if contract is None or contract.judgeability != HumanJudgeability.ELIGIBLE:
            return self._result(entity, proposition_id, [PresentationReason.PROPOSITION_NOT_HUMAN_JUDGEABLE], {})
        try:
            resolved, beatmap, audio_ms = self._map(checksum)
            normalized = normalize(beatmap)
        except (OSError, ValueError, OverflowError):
            return self._result(entity, proposition_id, [PresentationReason.MAP_ASSET_UNAVAILABLE], {})
        if beatmap.mode != 0:
            reasons.append(PresentationReason.UNSUPPORTED_MODE.value)
        if resolved.audio_path is None:
            reasons.append(PresentationReason.AUDIO_UNAVAILABLE.value)
        elif audio_ms is None:
            reasons.append(PresentationReason.AUDIO_DURATION_UNAVAILABLE.value)
        timing_values = []
        for point in beatmap.timing_points:
            timing_values.extend((point.time_ms, point.beat_length_ms))
            if point.bpm is not None:
                timing_values.append(point.bpm)
                if point.bpm <= 0 or point.bpm > MAX_PRESENTATION_BPM:
                    reasons.append(PresentationReason.BPM_PRESENTATION_UNSAFE.value)
            if not point.uninherited:
                timing_values.append(point.sv)
                if point.sv <= 0 or point.sv > MAX_PRESENTATION_SV:
                    reasons.append(PresentationReason.SV_PRESENTATION_UNSAFE.value)
            if point.degenerate:
                reasons.append(PresentationReason.TIMING_NONFINITE.value)
        if any(not math.isfinite(float(value)) for value in timing_values):
            reasons.append(PresentationReason.TIMING_NONFINITE.value)
        try:
            start_ms, end_ms = self._window(ref, normalized)
        except (KeyError, TypeError, ValueError):
            reasons.append(PresentationReason.INVALID_PRESENTATION_WINDOW.value)
            start_ms, end_ms = 0.0, 0.0
        if not all(math.isfinite(value) for value in (start_ms, end_ms)) or start_ms < 0 or end_ms <= start_ms:
            reasons.append(PresentationReason.INVALID_PRESENTATION_WINDOW.value)
        if end_ms - start_ms > MAX_INTERACTIVE_TIMELINE_MS:
            reasons.append(PresentationReason.TIMELINE_TOO_LONG.value)
        if audio_ms is not None and end_ms > audio_ms + AUDIO_COVERAGE_TOLERANCE_MS:
            reasons.append(PresentationReason.AUDIO_WINDOW_UNCOVERED.value)
        if ref["scope"] == "SEGMENT":
            canonical = LocalSignalExtractor().extract(beatmap)["segments"]
            resolved_segment = any(
                index == int(ref["segment_index"])
                and math.isclose(float(row["start_ms"]), float(ref["segment_start_ms"]), abs_tol=1e-6)
                and math.isclose(float(row["end_ms"]), float(ref["segment_end_ms"]), abs_tol=1e-6)
                for index, row in enumerate(canonical)
            )
            if not resolved_segment:
                reasons.append(PresentationReason.CANONICAL_SEGMENT_UNRESOLVED.value)
        relevant = [
            row for row in normalized.objects
            if row.canonical_end_time_ms() >= start_ms and row.raw.time_ms <= end_ms
        ]
        sliders = 0
        for row in relevant:
            raw = row.raw
            values = (raw.x, raw.y, raw.time_ms, row.canonical_end_time_ms())
            if any(not math.isfinite(float(value)) for value in values):
                reasons.append(PresentationReason.OBJECT_TIME_UNREPRESENTABLE.value)
            if not 0 <= raw.x <= 512 or not 0 <= raw.y <= 384:
                reasons.append(PresentationReason.OBJECT_OUTSIDE_RENDERER.value)
            if raw.object_type != "slider":
                continue
            sliders += 1
            relative = [(0.0, 0.0)] + [
                (float(x) - float(raw.x), float(y) - float(raw.y))
                for x, y in raw.slider_points
            ]
            try:
                path = build_slider_path(raw.slider_curve_type, relative, raw.slider_pixel_length)
                points = path.calculated_path
            except (TypeError, ValueError, OverflowError):
                points = ()
            if len(points) < 2 or any(not math.isfinite(value) for point in points for value in point):
                reasons.append(PresentationReason.SLIDER_GEOMETRY_UNRENDERABLE.value)
            duration = row.canonical_end_time_ms() - row.raw.time_ms
            if not math.isfinite(duration) or duration <= 0 or not isinstance(raw.slider_slides, int) or raw.slider_slides < 1:
                reasons.append(PresentationReason.SLIDER_TRAVERSAL_UNREPRESENTABLE.value)
        if (
            contract.empty_domain_policy == EmptyDomainPolicy.PAIR_INELIGIBLE
            and sliders == 0
        ):
            reasons.append(PresentationReason.EMPTY_PROPOSITION_DOMAIN.value)
        diagnostics = {
            "audio_duration_ms": round(audio_ms, 3) if audio_ms is not None else None,
            "presentation_window": {"start_ms": round(start_ms, 3), "end_ms": round(end_ms, 3)},
            "timeline_duration_ms": round(end_ms - start_ms, 3),
            "relevant_object_count": len(relevant),
            "relevant_slider_count": sliders,
            "challenge_categories_ignored_for_decision": list(entity.get("challenge_categories", ())),
        }
        return self._result(entity, proposition_id, reasons, diagnostics)

    @staticmethod
    def _result(entity: Mapping[str, Any], proposition_id: str, reasons: list[Any], diagnostics: Mapping[str, Any]) -> dict[str, Any]:
        normalized = sorted({reason.value if isinstance(reason, PresentationReason) else str(reason) for reason in reasons})
        return {
            "eligibility_version": PRESENTATION_ELIGIBILITY_VERSION,
            "display_id": entity.get("anonymous_display_id"),
            "proposition_id": proposition_id,
            "eligible": not normalized,
            "reasons": normalized,
            "diagnostics": dict(diagnostics),
        }

    def evaluate_pair(self, task: Mapping[str, Any]) -> dict[str, Any]:
        proposition = str(task["proposition"]["key"])
        sides = {
            side: self.evaluate_entity(task[f"entity_{side}"], proposition)
            for side in ("a", "b")
        }
        return {
            "eligibility_version": PRESENTATION_ELIGIBILITY_VERSION,
            "task_id": task.get("task_id"),
            "eligible": all(row["eligible"] for row in sides.values()),
            "sides": sides,
        }


__all__ = [
    "PRESENTATION_ELIGIBILITY_VERSION",
    "HUMAN_PROPOSITION_CONTRACT_VERSION",
    "MAX_INTERACTIVE_TIMELINE_MS",
    "MAX_PRESENTATION_BPM",
    "MAX_PRESENTATION_SV",
    "AUDIO_COVERAGE_TOLERANCE_MS",
    "EmptyDomainPolicy",
    "HumanJudgeability",
    "PresentationReason",
    "HumanPropositionContract",
    "HUMAN_PROPOSITIONS",
    "audio_duration_ms",
    "HumanPresentationEligibility",
]
