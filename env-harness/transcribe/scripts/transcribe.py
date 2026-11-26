#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

import requests
import dashscope
from dashscope import Files

import sys as _sys
from pathlib import Path as _Path

_SCRIPT_DIR = _Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPT_DIR))
import silence_map  # noqa: E402  (sibling module; needs script dir on path)
import env_loader  # noqa: E402  (sibling module; env > skills.env fallback)
del _sys, _Path

SUPPORTED_FORMATS = {".mp4", ".mp3", ".wav", ".m4a", ".flac", ".avi", ".mkv", ".mov"}


@dataclass(frozen=True)
class DiarizeChunk:
    """One <=2h slice of the uploaded audio, with its offset into the whole."""

    path: Path
    offset_seconds: float
RETRY_DELAYS = [1, 2, 4]  # exponential backoff in seconds
PENDING_STATUSES = {"PENDING", "RUNNING"}
DEFAULT_POLL_TIMEOUT = 600  # seconds; auto-scales with audio length


def compute_poll_timeout(audio_seconds: float, override: float | None = None) -> int:
    """Polling budget in seconds: explicit override wins, else auto-scale.

    ASR wall time grows roughly linearly with audio length, so a fixed 600s
    ceiling times out on long recordings that are still being processed.
    Auto rule: max(DEFAULT_POLL_TIMEOUT, audio_seconds / 4) — 2h43m audio
    (9811s) gets a ~41 min budget.
    """
    if override and override > 0:
        return max(1, int(override))
    if audio_seconds and audio_seconds > 0:
        return max(DEFAULT_POLL_TIMEOUT, int(audio_seconds / 4))
    return DEFAULT_POLL_TIMEOUT


def _retry_with_backoff(func, retries: int = 3, delays: list[int] | None = None):
    """Execute func with exponential backoff retry."""
    delays = delays or RETRY_DELAYS
    last_exception = None
    for attempt in range(retries):
        try:
            return func()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            last_exception = e
            if attempt < retries - 1:
                time.sleep(delays[min(attempt, len(delays) - 1)])
    raise last_exception


class MeetingTranscriber:
    def __init__(
        self,
        input_file: str,
        output_dir: str | None = None,
        poll_timeout: float | None = None,
        trim_silence: bool = True,
        trim_threshold: float = silence_map.TRIM_THRESHOLD_DEFAULT,
        diarize: bool = False,
        speaker_count: int | None = None,
    ):
        self.input_file = Path(input_file)
        self.output_dir = self._derive_output_dir(output_dir)
        self.temp_wav: Path | None = None
        self.task_id: str | None = None
        self.poll_timeout = poll_timeout
        self.audio_seconds: float = 0.0
        self.trim_silence = trim_silence
        self.trim_threshold = trim_threshold
        self.diarize = diarize
        self.speaker_count = speaker_count
        self.time_map: silence_map.TimeMap | None = None
        self._last_trim_cmd: list[str] = []

    def run(self) -> Path:
        try:
            self._validate_environment()
            self._normalize_audio()
            decision, time_map = self._scan_silence()
            if time_map is not None:
                self.time_map = time_map
                self.temp_wav = self._write_trimmed_wav(
                    time_map,
                    self.temp_wav.with_name(self.temp_wav.stem + "_trimmed.wav"),
                )
                self.audio_seconds = self._wav_seconds(self.temp_wav)
            if self.diarize and self.audio_seconds > 2 * 3600:
                result = self._transcribe_diarize_chunked()
            else:
                oss_url = self._upload_to_oss()
                task_id = self._submit_asr_task(oss_url)
                result = self._poll_result(task_id)
            uploaded_md = self._generate_markdown(result)
            md_path = self._finalize_transcript(uploaded_md)
            self._cleanup(success=True)
            return md_path
        except BaseException:
            # BaseException so KeyboardInterrupt/SystemExit also clean up the
            # temp WAV (hundreds of MB for long recordings) on Ctrl-C.
            self._cleanup(success=False)
            raise

    def _transcribe_diarize_chunked(self) -> dict:
        """Diarize long audio: cut into <=2h chunks, submit each, merge
        sentences with each chunk's time offset applied to begin/end."""
        merged: list[dict] = []
        for i, chunk in enumerate(self._diarize_chunks(), start=1):
            print(
                "diarize 分块 {}/{}: offset {:.0f}s".format(
                    i, len(self._diarize_chunks()), chunk.offset_seconds
                )
            )
            self.temp_wav = chunk.path
            oss_url = self._upload_to_oss()
            task_id = self._submit_asr_task(oss_url)
            result = self._poll_result(task_id)
            sentences = (
                result.get("output", {}).get("transcription", {}).get("sentences", [])
            )
            offset_ms = int(chunk.offset_seconds * 1000)
            for sent in sentences:
                shifted = dict(sent)
                shifted["begin_time"] = sent.get("begin_time", 0) + offset_ms
                shifted["end_time"] = sent.get("end_time", 0) + offset_ms
                merged.append(shifted)
        return {"output": {"transcription": {"sentences": merged}}}

    def _diarize_chunks(self):
        """Split audio into <=2h chunks for paraformer-v2 diarization.

        The 2h recommendation is a model-side quality constraint; longer
        audio degrades speaker-clustering quality. Returns immutable
        chunk descriptors (path, offset) in temporal order.
        """
        chunk_limit = 2 * 3600.0
        n = int(self.audio_seconds // chunk_limit) + 1
        if n <= 1:
            return (DiarizeChunk(self.temp_wav, 0.0),)
        chunks = []
        for i in range(n):
            start = i * chunk_limit
            duration = min(chunk_limit, self.audio_seconds - start)
            if duration <= 0:
                break
            path = self._cut_chunk(start, duration)
            chunks.append(DiarizeChunk(path, start))
        return tuple(chunks)

    def _cut_chunk(self, start: float, duration: float) -> Path:
        """Cut [start, start+duration) out of the normalized WAV."""
        if not self.temp_wav or not self.temp_wav.exists():
            raise RuntimeError("No WAV to chunk")
        out = self.temp_wav.with_name(
            self.temp_wav.stem + "_part{:.0f}.wav".format(start)
        )
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-ss", "{:.3f}".format(start), "-t", "{:.3f}".format(duration),
            "-i", str(self.temp_wav),
            "-acodec", "copy", str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("ffmpeg chunk cut failed: {}".format(e.stderr)) from e
        return out

    def _scan_silence(self):
        """Scan the normalized WAV for silence; build a trim map when due.

        Trimming is the DEFAULT (all-day recordings carry minutes-scale dead
        air that costs upload time and billed seconds). Disable with
        trim_silence=False. Returns (decision, None) when no trim is due.
        """
        if not self.trim_silence or not self.temp_wav:
            return None, None
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner",
                "-i", str(self.temp_wav),
                "-map", "0:a:0", "-vn",
                "-af", "silencedetect=noise={:.1f}dB:d={:.1f}".format(
                    silence_map.SILENCE_NOISE_FLOOR, silence_map.MIN_SILENCE_SECONDS
                ),
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=max(600, int(self.audio_seconds) + 60),
        )
        silences = silence_map.parse_silencedetect_log(
            proc.stderr, total_duration=self.audio_seconds
        )
        decision = silence_map.trim_decision(self.audio_seconds, silences)
        if not decision.should_trim:
            print(
                "静音扫描: {} 段共 {:.0f}s ({:.1f}%), 无需裁剪".format(
                    len(silences), decision.total_silence, decision.silence_share * 100
                )
            )
            return decision, None
        time_map = silence_map.build_from_silences(
            self.audio_seconds, silences, self.trim_threshold
        )
        print(
            "静音扫描: {} 段共 {:.0f}s ({:.1f}%), 最长 {:.0f}s → 裁剪后上传 {:.0f}s / 原 {:.0f}s".format(
                len(silences), decision.total_silence, decision.silence_share * 100,
                decision.longest, time_map.total_uploaded, decision.total_duration,
            )
        )
        return decision, time_map

    def _write_trimmed_wav(self, time_map, out_path):
        """Materialize the trimmed WAV: concat the kept spans with ffmpeg."""
        if not self.temp_wav or not self.temp_wav.exists():
            raise RuntimeError("No normalized WAV to trim")
        inputs = []
        for span in time_map.spans:
            inputs += [
                "-ss", "{:.3f}".format(span.original_start),
                "-t", "{:.3f}".format(span.original_end - span.original_start),
                "-i", str(self.temp_wav),
            ]
        n = len(time_map.spans)
        filter_parts = [
            "[{}:a]atrim=start=0,asetpts=PTS-STARTPTS[a{}]".format(i, i)
            for i in range(n)
        ]
        filter_parts.append(
            "".join("[a{}]".format(i) for i in range(n))
            + "concat=n={}:v=0:a=1[out]".format(n)
        )
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[out]", "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(out_path),
        ]
        self._last_trim_cmd = cmd
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("ffmpeg trim failed: {}".format(e.stderr)) from e
        if not out_path.exists():
            raise RuntimeError("trim produced no output file")
        return out_path

    def _finalize_transcript(self, uploaded_md):
        """Remap transcript to original-media time when a trim happened,
        persist the time-axis map JSON, and run the voiced verification."""
        if self.time_map is None:
            return uploaded_md
        remapped = uploaded_md.with_name(uploaded_md.stem + "_原片时间.md")
        silence_map.remap_transcript(uploaded_md, self.time_map, remapped)
        map_json = uploaded_md.with_name(
            uploaded_md.stem.replace("_字幕", "") + "_时间轴映射.json"
        )
        map_json.write_text(
            silence_map.time_map_to_json(self.time_map), encoding="utf-8"
        )
        report = silence_map.verify_transcript(
            remapped, self.input_file, sample=5
        )
        print(
            "时间轴还原验收: 抽检 {} 段, 有声 {}, 静音 {}".format(
                report.total, report.voiced, report.silent
            )
        )
        if report.silent > 0:
            details = ", ".join("[{} - {}]".format(b, e) for b, e in report.silent_times)
            print("警告: 以下时间戳疑似未落回有声区: {}".format(details))
        return remapped

    def _derive_output_dir(self, output_dir: str | None) -> Path:
        if output_dir:
            return Path(output_dir)
        project_root = self._find_project_root()
        for candidate in ["raw/会议纪要", "output"]:
            path = project_root / candidate
            if path.exists():
                return path / "transcribe"
        return project_root / "output" / "transcribe"

    def _find_project_root(self) -> Path:
        # Prefer input file's location for cross-project scenarios
        start_path = self.input_file.parent
        for parent in [start_path, *start_path.parents]:
            if (parent / ".git").exists() or (parent / "CLAUDE.md").exists():
                return parent
        # Fallback to cwd if input file is not in any project
        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            if (parent / ".git").exists() or (parent / "CLAUDE.md").exists():
                return parent
        return cwd

    def _validate_environment(self) -> None:
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        if self.input_file.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format: {self.input_file.suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )
        if not shutil.which("ffmpeg"):
            raise EnvironmentError("ffmpeg not found in PATH. Please install ffmpeg.")
        try:
            api_key = env_loader.get_required("DASHSCOPE_API_KEY")
        except env_loader.MissingEnvError as exc:
            raise EnvironmentError(str(exc)) from exc
        # dashscope SDK 只认 os.environ；回退链取到值后注入本进程，供 SDK 使用
        if not os.environ.get("DASHSCOPE_API_KEY"):
            os.environ["DASHSCOPE_API_KEY"] = api_key

    def _normalize_audio(self) -> Path:
        suffix = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        temp_path = Path(tempfile.gettempdir()) / f"{self.input_file.stem}{suffix}"
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(self.input_file),
            "-ar", "16000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            str(temp_path)
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg failed: {e.stderr}") from e
        self.temp_wav = temp_path
        self.audio_seconds = self._wav_seconds(temp_path)
        return temp_path

    @staticmethod
    def _wav_seconds(path: Path) -> float:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())

    def _upload_to_oss(self) -> str:
        if not self.temp_wav or not self.temp_wav.exists():
            raise RuntimeError("No temp WAV file to upload. Call _normalize_audio first.")

        def _do_upload():
            resp = Files.upload(
                file_path=str(self.temp_wav),
                purpose="file-extract",
                description="meeting transcript audio"
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Files.upload failed: {resp}")
            file_id = resp.output["uploaded_files"][0]["file_id"]
            info = Files.get(file_id)
            if info.status_code != 200:
                raise RuntimeError(f"Files.get failed: {info}")
            return info.output["url"]

        return _retry_with_backoff(_do_upload, retries=3)

    def _submit_asr_task(self, oss_url: str) -> str:
        def _do_call():
            api_key = env_loader.get_required("DASHSCOPE_API_KEY")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable"
            }
            if self.diarize:
                parameters = {
                    "channel_id": [0],
                    "diarization_enabled": True,
                    "language_hints": ["zh"],
                }
                if self.speaker_count:
                    parameters["speaker_count"] = self.speaker_count
                payload = {
                    "model": "paraformer-v2",
                    "input": {"file_urls": [oss_url]},
                    "parameters": parameters,
                }
            else:
                payload = {
                    "model": "qwen3-asr-flash-filetrans",
                    "input": {"file_url": oss_url},
                    "parameters": {
                        "channel_id": [0],
                        "enable_itn": True,
                        "enable_words": False
                    }
                }
            resp = requests.post(
                "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"Invalid API response: missing task_id. Response: {data}")
            return task_id

        task_id = _retry_with_backoff(_do_call, retries=3)
        self.task_id = task_id
        return task_id

    def _poll_result(self, task_id: str) -> dict:
        api_key = env_loader.get_required("DASHSCOPE_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        start_time = time.time()
        timeout = compute_poll_timeout(self.audio_seconds, self.poll_timeout)
        interval = 15
        poll_retry_delays = [15, 30, 60]
        retry_count = 0

        while True:
            try:
                resp = requests.get(url, headers=headers, timeout=(10, 30))
                resp.raise_for_status()
                data = resp.json()
                status = data.get("output", {}).get("task_status", "")
                if status == "SUCCEEDED":
                    return self._resolve_result(data, task_id)
                elif status == "FAILED":
                    msg = data.get("output", {}).get("message", "Unknown error")
                    raise RuntimeError(self._failure_message(msg))
                elif status and status not in PENDING_STATUSES:
                    # Unknown statuses are treated as terminal: spinning until
                    # the timeout would misreport them as a timeout.
                    raise RuntimeError(
                        f"ASR task ended with unexpected status {status!r}. Response: {data}"
                    )
                elif time.time() - start_time >= timeout:
                    raise TimeoutError(
                        f"Polling timeout ({timeout // 60} min, audio {self.audio_seconds:.0f}s). "
                        f"Query manually: https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
                    )
                time.sleep(interval)
                retry_count = 0
            except (requests.RequestException, TimeoutError) as e:
                if isinstance(e, TimeoutError):
                    raise
                if retry_count >= len(poll_retry_delays):
                    raise RuntimeError(f"Network error after retries: {e}")
                time.sleep(poll_retry_delays[retry_count])
                retry_count += 1

    @staticmethod
    def _failure_message(msg: str) -> str:
        if "NO_VALID_FRAGMENT" in msg:
            return (
                f"ASR task found no valid speech fragment (status: {msg}). "
                "The audio is likely pure silence or dead air — a long lead-in from a "
                "device started before the speakers is common. Scan with "
                "`ffmpeg -af silencedetect=noise=-45dB:d=3 -f null -` and trim silent "
                "sections before re-uploading."
            )
        return f"ASR task failed: {msg}"

    def _download_json(self, url: str) -> dict:
        """GET a JSON document with retry."""
        def _do_download():
            resp = requests.get(url, timeout=(10, 60))
            resp.raise_for_status()
            return resp.json()

        return _retry_with_backoff(_do_download, retries=3)

    def _resolve_result(self, data: dict, task_id: str | None = None) -> dict:
        output = data.get("output", {})
        # paraformer-v2 returns output.results[] (plural): one entry per
        # input file, each with its own transcription_url
        results = output.get("results")
        if results:
            sentences = []
            for item in results:
                url = item.get("transcription_url")
                if not url:
                    continue
                transcript_data = self._download_json(url)
                for transcript in transcript_data.get("transcripts", []):
                    sentences.extend(transcript.get("sentences", []))
            return {"output": {"transcription": {"sentences": sentences}}}
        # qwen3-asr-flash-filetrans returns transcription_url instead of inline sentences
        transcription_url = output.get("result", {}).get("transcription_url")
        if transcription_url:
            try:
                transcript_data = self._download_json(transcription_url)
            except Exception:
                # URL expired fallback: fetch fresh URL via SDK
                try:
                    from dashscope.audio.asr import Transcription
                    fresh_resp = Transcription.fetch(task=task_id)
                    if fresh_resp.status_code == 200:
                        fresh_url = (
                            fresh_resp.output.get("result", {})
                            .get("transcription_url")
                        )
                        if fresh_url:
                            resp = requests.get(fresh_url, timeout=(10, 60))
                            resp.raise_for_status()
                            transcript_data = resp.json()
                        else:
                            raise RuntimeError(
                                f"fetch() returned no transcription_url. task_id={task_id}"
                            )
                    else:
                        raise RuntimeError(
                            f"Transcription.fetch failed: {fresh_resp}. task_id={task_id}"
                        )
                except Exception as fetch_err:
                    raise RuntimeError(
                        f"Failed to download transcription result and fetch() also failed. "
                        f"task_id={task_id}. Original error: {fetch_err}"
                    ) from fetch_err

            sentences = []
            for transcript in transcript_data.get("transcripts", []):
                sentences.extend(transcript.get("sentences", []))
            return {"output": {"transcription": {"sentences": sentences}}}
        # paraformer-v1 returns inline results
        return data

    def _generate_markdown(self, result: dict) -> Path:
        lines = [f"# {self.input_file.stem} 会议字幕", ""]
        lines.append("- 音频格式: wav")
        lines.append("- 采样率: 16000")
        lines.append("")

        sentences = result.get("output", {}).get("transcription", {}).get("sentences", [])
        for i, sent in enumerate(sentences):
            begin = self._ms_to_hhmmss(sent["begin_time"])
            end = self._ms_to_hhmmss(sent["end_time"])
            speaker = sent.get("speaker_id")
            if speaker is not None:
                # paraformer-v2 returns an int; qwen3-asr-flash-filetrans
                # legacy form was "SpeakerN" strings
                if isinstance(speaker, int):
                    speaker_num = str(speaker + 1)
                else:
                    digits = "".join(filter(str.isdigit, str(speaker)))
                    speaker_num = digits or "1"
                header = f"**[{begin} - {end}] 说话人{speaker_num}**"
            else:
                header = f"**[{begin} - {end}] 片段{i + 1}**"
            text = sent.get("text", "")
            lines.append(header)
            lines.append("")
            lines.append(f"> {text}")
            lines.append("")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.input_file.stem}_字幕_{timestamp}.md"
        md_path = self.output_dir / filename
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return md_path

    def _cleanup(self, success: bool) -> None:
        # Delete the temp WAV on both paths: it is re-derivable from the
        # source via ffmpeg, and keeping it leaks hundreds of MB per failure.
        if self.temp_wav and self.temp_wav.exists():
            self.temp_wav.unlink()

    @staticmethod
    def _ms_to_hhmmss(ms: int) -> str:
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def main():
    parser = argparse.ArgumentParser(description="Meeting transcript generator")
    parser.add_argument("input_file", help="Input audio/video file path")
    parser.add_argument("--output-dir", help="Output directory for the transcript (optional)")
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=None,
        help="Polling timeout in seconds (default: auto — at least 600s, scaled by audio length; must be positive)",
    )
    parser.add_argument(
        "--no-trim",
        action="store_true",
        help="Disable silence trimming (trimming long silences before upload is the default)",
    )
    parser.add_argument(
        "--trim-threshold",
        type=float,
        default=None,
        help="Silences shorter than this many seconds stay in place (default: 20)",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable speaker separation (paraformer-v2 + diarization_enabled)",
    )
    parser.add_argument(
        "--speakers",
        type=int,
        default=None,
        help="Known speaker count for --diarize (2-100); omit to auto-detect",
    )
    args = parser.parse_args()
    if args.speakers is not None and not (2 <= args.speakers <= 100):
        parser.error("--speakers must be between 2 and 100")
    if args.poll_timeout is not None and args.poll_timeout <= 0:
        parser.error("--poll-timeout must be a positive number of seconds")
    if args.trim_threshold is not None and args.trim_threshold <= 0:
        parser.error("--trim-threshold must be positive")
    transcriber = MeetingTranscriber(
        args.input_file,
        args.output_dir,
        poll_timeout=args.poll_timeout,
        trim_silence=not args.no_trim,
        trim_threshold=args.trim_threshold
        if args.trim_threshold is not None
        else silence_map.TRIM_THRESHOLD_DEFAULT,
        diarize=args.diarize,
        speaker_count=args.speakers,
    )
    md_path = transcriber.run()
    task_info = f" (task_id={transcriber.task_id})" if transcriber.task_id else ""
    print(f"Transcript written to: {md_path}{task_info}")


if __name__ == "__main__":
    main()
