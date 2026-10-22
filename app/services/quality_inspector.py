import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def probe_media(path: Path) -> dict:
    """Read media duration and stream information using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name",
            "-of", "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media duration is invalid.")

    streams = data.get("streams", [])
    return {
        "duration_seconds": round(duration, 3),
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "audio_codecs": [
            s.get("codec_name")
            for s in streams
            if s.get("codec_type") == "audio"
        ],
    }


def build_quality_report(
    source_video: Path,
    dubbed_audio: Path,
    output_video: Path,
    transcript_segment_count: int,
    report_path: Path,
) -> dict:
    """Inspect generated media and save a JSON quality report."""
    source_video = Path(source_video).resolve()
    dubbed_audio = Path(dubbed_audio).resolve()
    output_video = Path(output_video).resolve()
    report_path = Path(report_path).resolve()

    checks = []
    warnings = []
    metrics = {}

    def add_check(check_id, label, passed, summary):
        checks.append({
            "id": check_id,
            "label": label,
            "status": "passed" if passed else "warning",
            "summary": summary,
        })

    try:
        source = probe_media(source_video)
        metrics["source_duration_seconds"] = source["duration_seconds"]
        add_check(
            "source_readable",
            "Original video",
            source["has_video"],
            "Original video is readable."
            if source["has_video"]
            else "Original file has no video stream.",
        )
        if not source["has_video"]:
            warnings.append("Original file has no video stream.")

        audio = probe_media(dubbed_audio)
        metrics["dubbed_audio_duration_seconds"] = audio["duration_seconds"]
        add_check(
            "dubbed_audio_readable",
            "Dubbed audio",
            audio["has_audio"],
            "Dubbed audio is readable."
            if audio["has_audio"]
            else "Dubbed audio file has no audio stream.",
        )
        if not audio["has_audio"]:
            warnings.append("Dubbed audio file has no audio stream.")

        output = probe_media(output_video)
        metrics["output_video_duration_seconds"] = output["duration_seconds"]

        output_valid = output["has_video"] and output["has_audio"]
        add_check(
            "output_media_valid",
            "Final dubbed video",
            output_valid,
            "Final video contains video and audio streams."
            if output_valid
            else "Final video is missing a video or audio stream.",
        )
        if not output_valid:
            warnings.append("Final video is missing a required media stream.")

        duration_difference = abs(
            source["duration_seconds"] - output["duration_seconds"]
        )
        metrics["source_output_duration_difference_seconds"] = round(
            duration_difference, 3
        )
        duration_ok = duration_difference <= max(
            1.0, source["duration_seconds"] * 0.02
        )
        add_check(
            "duration_match",
            "Video duration match",
            duration_ok,
            "Output duration is close to the source duration."
            if duration_ok
            else "Output duration differs noticeably from the source.",
        )
        if not duration_ok:
            warnings.append(
                "Output video duration differs from the original video."
            )

        metrics["transcript_segment_count"] = int(transcript_segment_count)
        segments_ok = transcript_segment_count > 0
        add_check(
            "speech_segments",
            "Speech segments",
            segments_ok,
            f"{transcript_segment_count} speech segments processed."
            if segments_ok
            else "No transcript speech segments were recorded.",
        )
        if not segments_ok:
            warnings.append("No transcript speech segments were recorded.")

    except Exception as error:
        warnings.append(f"One or more media checks could not finish: {error}")
        checks.append({
            "id": "inspection_complete",
            "label": "Inspection completeness",
            "status": "incomplete",
            "summary": "Some checks could not be completed.",
        })

    statuses = [item["status"] for item in checks]
    if "incomplete" in statuses:
        overall_status = "checks_incomplete"
    elif "warning" in statuses:
        overall_status = "review_recommended"
    else:
        overall_status = "passed"

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "checks": checks,
        "metrics": metrics,
        "warnings": warnings,
        "note": (
            "Automated media checks do not guarantee translation accuracy "
            "or lip-sync quality."
        ),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report
