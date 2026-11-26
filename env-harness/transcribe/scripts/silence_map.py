#!/usr/bin/env python3
"""Silence-trim time-axis mapping for meeting transcripts.

When long silences are trimmed before uploading to ASR, the transcript's
timestamps refer to the *uploaded* (trimmed) file, not the original media.
This module rebuilds the exact mapping between the two timelines:

- parse an ffmpeg `silencedetect` log into silence segments
- decide whether trimming is worthwhile (share > 5% or a segment > 60s)
- build a piecewise (or constant head-trim) offset map
- rewrite transcript Markdown timestamps back to original-media time
- verify: sample transcript segments and probe the ORIGINAL audio at the
  remapped times to confirm they land on speech (not silence)

All map objects are immutable; every operation returns new values.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --- tunables (deliberately wide: only minutes-scale dead air is worth acting on)
SILENCE_NOISE_FLOOR = -45.0  # dB below which audio counts as silence
MIN_SILENCE_SECONDS = 3.0  # segments shorter than this are not reported at all
TRIM_SHARE_THRESHOLD = 0.05  # trim when total silence > 5% of the recording
TRIM_SEGMENT_THRESHOLD = 60.0  # ... or when any single silence exceeds 60s
TRIM_THRESHOLD_DEFAULT = 20.0  # silences shorter than this are kept in place
VERIFY_VOICED_FLOOR_DB = -45.0  # segment counts as speech when mean volume above

_HHMMSS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})$")
_SILENCE_START = re.compile(r"silence_start:\s*(\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end:\s*(\d+(?:\.\d+)?)")
_MD_TIMESTAMP = re.compile(r"\[(\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\]")


@dataclass(frozen=True)
class SilenceSegment:
    """A closed-ish interval [start, end) of silence in the source media."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class TrimDecision:
    total_duration: float
    total_silence: float
    silence_share: float
    longest: float
    should_trim: bool


def hhmmss_to_seconds(text: str) -> float:
    m = _HHMMSS_RE.match(text.strip())
    if not m:
        raise ValueError(f"Invalid HH:MM:SS timestamp: {text!r}")
    h, mi, s = m.groups()
    return float(h) * 3600 + float(mi) * 60 + float(s)


def seconds_to_hhmmss(seconds: float) -> str:
    if seconds < 0:
        raise ValueError(f"Negative time: {seconds}")
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    mi, s = divmod(rem, 60)
    return f"{h:02d}:{mi:02d}:{s:02d}"


# ---------------------------------------------------------------- logging parse


def parse_silencedetect_log(log: str, total_duration: float | None = None) -> tuple[SilenceSegment, ...]:
    """Parse ffmpeg silencedetect stderr into immutable silence segments.

    An unmatched trailing silence_start runs to total_duration (a file that
    ends in silence never emits silence_end).
    """
    segments: list[SilenceSegment] = []
    open_start: float | None = None
    for line in log.splitlines():
        end_m = _SILENCE_END.search(line)
        if end_m:
            end = float(end_m.group(1))
            if open_start is None:
                continue  # orphan end without start: unusable, skip
            segment = SilenceSegment(open_start, end)
            if segment.duration <= 0:
                raise ValueError(
                    f"Silence segment end <= start: {open_start}..{end}"
                )
            segments.append(segment)
            open_start = None
            continue
        start_m = _SILENCE_START.search(line)
        if start_m:
            open_start = float(start_m.group(1))
    if open_start is not None:
        if total_duration is None:
            raise ValueError(
                "Trailing silence_start without silence_end and no total_duration; "
                "cannot close the segment. Pass total_duration."
            )
        segments.append(SilenceSegment(open_start, total_duration))
    return tuple(segments)


def trim_decision(
    total_duration: float, silences: tuple[SilenceSegment, ...]
) -> TrimDecision:
    """Whether trimming is worthwhile, per the two published criteria."""
    total_silence = sum(s.duration for s in silences)
    longest = max((s.duration for s in silences), default=0.0)
    share = total_silence / total_duration if total_duration > 0 else 0.0
    should = (
        share > TRIM_SHARE_THRESHOLD
        or longest > TRIM_SEGMENT_THRESHOLD
    )
    return TrimDecision(total_duration, total_silence, share, longest, should)


# ---------------------------------------------------------------- offset maps


@dataclass(frozen=True)
class _Span:
    """One kept (non-silent) span of the original media, mapped to the
    uploaded timeline as [0, len)."""

    original_start: float
    original_end: float
    uploaded_start: float

    def to_original(self, t: float) -> float:
        return self.original_start + (t - self.uploaded_start)

    def to_uploaded(self, t: float) -> float:
        return self.uploaded_start + (t - self.original_start)


@dataclass(frozen=True)
class TimeMap:
    """Immutable mapping between uploaded (trimmed) and original timelines."""

    spans: tuple[_Span, ...]
    total_original: float
    total_uploaded: float

    def to_original(self, t: float) -> float:
        """Uploaded time -> original time. Boundary times belong to the span
        that STARTS there; times beyond the uploaded span clamp to the end."""
        if t >= self.total_uploaded:
            return self.spans[-1].original_end
        for span in self.spans:
            span_end_up = span.uploaded_start + (span.original_end - span.original_start)
            if t < span_end_up:
                return span.to_original(t)
        return self.spans[-1].original_end

    def to_uploaded(self, t: float) -> float:
        """Original time -> uploaded time. Times in trimmed silences map to
        the uploaded position where the silence was removed. Boundary times
        belong to the span that STARTS there (half-open [start, end))."""
        if t >= self.total_original:
            return self.total_uploaded
        for span in self.spans:
            if t < span.original_end:
                if t < span.original_start:
                    # in the trimmed silence before this span: collapse to
                    # the span start
                    return span.to_uploaded(span.original_start)
                return span.to_uploaded(t)
        return self.total_uploaded


def build_constant_offset(head_trim: float, total_original: float) -> TimeMap:
    if head_trim < 0:
        raise ValueError(f"head_trim must be >= 0, got {head_trim}")
    if head_trim >= total_original:
        raise ValueError(
            f"head_trim ({head_trim}) must be < total_original ({total_original})"
        )
    span = _Span(
        original_start=head_trim,
        original_end=total_original,
        uploaded_start=0.0,
    )
    return TimeMap(
        spans=(span,),
        total_original=total_original,
        total_uploaded=total_original - head_trim,
    )


def build_from_silences(
    total_duration: float,
    silences: tuple[SilenceSegment, ...],
    trim_threshold: float = TRIM_THRESHOLD_DEFAULT,
) -> TimeMap:
    """Piecewise map: drop silences longer than trim_threshold, keep the rest.

    Silences shorter than the threshold stay in place, so the mapping is
    identity across them — ordinary conversational pauses never shift.
    """
    big = sorted(
        (s for s in silences if s.duration > trim_threshold), key=lambda s: s.start
    )
    spans: list[_Span] = []
    cursor_orig = 0.0  # current position in original timeline
    cursor_up = 0.0  # current position in uploaded timeline
    for seg in big:
        if seg.start < cursor_orig:
            # overlapping/adjacent segments: skip (already consumed)
            continue
        if seg.start > cursor_orig:
            spans.append(
                _Span(cursor_orig, seg.start, cursor_up)
            )
            cursor_up += seg.start - cursor_orig
        cursor_orig = seg.end
    if cursor_orig < total_duration:
        spans.append(_Span(cursor_orig, total_duration, cursor_up))
        cursor_up += total_duration - cursor_orig
    return TimeMap(
        spans=tuple(spans),
        total_original=total_duration,
        total_uploaded=cursor_up,
    )


# ------------------------------------------------------- transcript rewriting


def remap_transcript(src: Path, map: TimeMap, out: Path, reverse: bool = False) -> Path:
    """Rewrite `[HH:MM:SS - HH:MM:SS]` headers in a transcript file.

    Forward (default): uploaded time -> original time (the usual fix-up after
    trimming before upload). Reverse: original -> uploaded.
    Writes a NEW file; never mutates the source.
    """
    convert = map.to_original if not reverse else map.to_uploaded

    def _rewrite(match: re.Match) -> str:
        begin = hhmmss_to_seconds(match.group(1))
        end = hhmmss_to_seconds(match.group(2))
        new_begin = convert(begin)
        new_end = convert(end)
        new_begin = max(0.0, new_begin)
        new_end = max(new_begin, new_end)
        return f"[{seconds_to_hhmmss(new_begin)} - {seconds_to_hhmmss(new_end)}]"

    text = src.read_text(encoding="utf-8")
    new_text = _MD_TIMESTAMP.sub(_rewrite, text)
    out.write_text(new_text, encoding="utf-8")
    return out


def time_map_to_json(map: TimeMap) -> str:
    """Serialize a TimeMap for persistence alongside the transcript."""
    return json.dumps(
        {
            "total_original": map.total_original,
            "total_uploaded": map.total_uploaded,
            "spans": [
                {
                    "original_start": s.original_start,
                    "original_end": s.original_end,
                    "uploaded_start": s.uploaded_start,
                }
                for s in map.spans
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def time_map_from_json(payload: dict) -> TimeMap:
    """Rebuild a TimeMap from its persisted JSON form."""
    spans = tuple(
        _Span(s["original_start"], s["original_end"], s["uploaded_start"])
        for s in payload["spans"]
    )
    return TimeMap(
        spans=spans,
        total_original=payload["total_original"],
        total_uploaded=payload["total_uploaded"],
    )


# --------------------------------------------------------------- verification


@dataclass(frozen=True)
class VerifyReport:
    total: int
    voiced: int
    silent: int
    silent_times: tuple[tuple[str, str], ...]


def verify_segment_voiced(media: str | Path, start: float, duration: float) -> bool:
    """Probe the ORIGINAL media at [start, start+duration) with volumedetect:
    mean volume above the floor => speech present."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-i", str(media),
        "-map", "0:a:0", "-vn",
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", proc.stderr)
    if not m:
        return False
    return float(m.group(1)) > VERIFY_VOICED_FLOOR_DB


def verify_transcript(
    transcript: Path, media: str | Path, sample: int = 5
) -> VerifyReport:
    """Acceptance check: sample transcript timestamps, probe the original
    media at those (remapped) times, confirm each lands on speech."""
    text = transcript.read_text(encoding="utf-8")
    stamps = _MD_TIMESTAMP.findall(text)
    if not stamps:
        raise ValueError(f"No timestamps found in {transcript}")
    if sample < 1:
        raise ValueError(f"sample must be >= 1, got {sample}")
    step = max(1, len(stamps) // sample)
    chosen = stamps[::step][:sample]
    voiced = 0
    silent_times: list[tuple[str, str]] = []
    for begin_s, end_s in chosen:
        begin = hhmmss_to_seconds(begin_s)
        end = hhmmss_to_seconds(end_s)
        duration = max(1.0, end - begin)
        if verify_segment_voiced(media, begin, min(duration, 10.0)):
            voiced += 1
        else:
            silent_times.append((begin_s, end_s))
    return VerifyReport(
        total=len(chosen),
        voiced=voiced,
        silent=len(silent_times),
        silent_times=tuple(silent_times),
    )


# ----------------------------------------------------------------------- CLI


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Silence-trim time-axis mapping for meeting transcripts"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="scan media for silence; report trim decision")
    scan.add_argument("media", help="input audio/video file")
    scan.add_argument("--threshold-seconds", type=float, default=MIN_SILENCE_SECONDS)

    p_map = sub.add_parser("map", help="build the offset map and rewrite a transcript")
    p_map.add_argument("media", help="ORIGINAL media file (silences are in its time)")
    p_map.add_argument("--log", default=None, help="path to ffmpeg silencedetect stderr log (required unless --constant)")
    p_map.add_argument("--transcript", required=True, help="transcript .md to rewrite (uploaded-time stamps)")
    p_map.add_argument("--out", default=None, help="output .md path (default: <transcript> without _uploaded suffix)")
    p_map.add_argument("--trim-threshold", type=float, default=TRIM_THRESHOLD_DEFAULT)
    p_map.add_argument("--constant", type=float, default=None,
                       help="use constant head-trim of this many seconds instead of piecewise")

    verify = sub.add_parser("verify", help="check remapped transcript against original media")
    verify.add_argument("media", help="ORIGINAL media file")
    verify.add_argument("--transcript", required=True, help="remapped transcript .md (original-time stamps)")
    verify.add_argument("--sample", type=int, default=5, help="number of segments to probe")

    args = parser.parse_args()

    if args.cmd == "scan":
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", args.media, "-map", "0:a:0", "-vn",
             "-af", f"silencedetect=noise={SILENCE_NOISE_FLOOR}dB:d={args.threshold_seconds}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=3600,
        )
        dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
        total = hhmmss_to_seconds(f"{dur_m.group(1)}:{dur_m.group(2)}:{int(float(dur_m.group(3))):02d}")
        silences = parse_silencedetect_log(proc.stderr, total_duration=total)
        d = trim_decision(total, silences)
        print(f"总时长: {seconds_to_hhmmss(total)} ({total:.0f}s)")
        print(f"静音段数: {len(silences)}")
        print(f"静音总时长: {d.total_silence:.0f}s ({d.total_silence/60:.1f} 分钟, {d.silence_share*100:.1f}%)")
        print(f"最长单段: {d.longest:.0f}s")
        print(f"判定: {'建议裁剪' if d.should_trim else '无需裁剪'}")
        return 0

    if args.cmd == "map":
        media = Path(args.media)
        if args.constant is not None:
            offset_map = build_constant_offset(args.constant, _media_duration(media))
        else:
            if not args.log:
                parser.error("--log is required for piecewise mapping (or use --constant)")
            log_text = Path(args.log).read_text(encoding="utf-8")
            silences = parse_silencedetect_log(log_text)
            offset_map = build_from_silences(
                _media_duration(media), silences, args.trim_threshold
            )
        src = Path(args.transcript)
        out = Path(args.out) if args.out else src.with_name(src.stem + "_remapped.md")
        remap_transcript(src, offset_map, out)
        print(
            f"已重映射 {src.name} -> {out.name} "
            f"(上传时长 {seconds_to_hhmmss(offset_map.total_uploaded)} / 原片 {seconds_to_hhmmss(offset_map.total_original)})"
        )
        return 0

    if args.cmd == "verify":
        report = verify_transcript(Path(args.transcript), args.media, args.sample)
        print(f"抽检 {report.total} 段: 有声 {report.voiced}, 静音 {report.silent}")
        if report.silent_times:
            print("落在静音区的时间戳（映射可能错误）:")
            for b, e in report.silent_times:
                print(f"  [{b} - {e}]")
            return 1
        print("验收通过：所有抽检时间戳均落在有声区")
        return 0

    return 0


def _media_duration(media: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, timeout=60,
    )
    return float(proc.stdout.strip())


if __name__ == "__main__":
    sys.exit(main())
