import json
from pathlib import Path

from app.services import quality_inspector


def probe_result(duration, has_video, has_audio):
    streams = []
    if has_video:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    if has_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})

    return {
        "format": {"duration": str(duration)},
        "streams": streams,
    }


def mock_probe_sequence(monkeypatch, results):
    def fake_run(*args, **kwargs):
        from types import SimpleNamespace

        data = results.pop(0)
        return SimpleNamespace(stdout=json.dumps(data))

    monkeypatch.setattr(quality_inspector.subprocess, "run", fake_run)


def test_quality_report_passes_for_valid_matching_media(
    monkeypatch, tmp_path
):
    mock_probe_sequence(
        monkeypatch,
        [
            probe_result(120, True, True),
            probe_result(120, False, True),
            probe_result(120.2, True, True),
        ],
    )

    report_path = tmp_path / "job" / "quality_report.json"
    report = quality_inspector.build_quality_report(
        tmp_path / "source.mp4",
        tmp_path / "dubbed.mp3",
        tmp_path / "output.mp4",
        12,
        report_path,
    )

    assert report["overall_status"] == "passed"
    assert report["metrics"]["transcript_segment_count"] == 12
    assert report_path.is_file()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["overall_status"] == "passed"


def test_quality_report_flags_duration_mismatch(monkeypatch, tmp_path):
    mock_probe_sequence(
        monkeypatch,
        [
            probe_result(120, True, True),
            probe_result(120, False, True),
            probe_result(105, True, True),
        ],
    )

    report = quality_inspector.build_quality_report(
        tmp_path / "source.mp4",
        tmp_path / "dubbed.mp3",
        tmp_path / "output.mp4",
        12,
        tmp_path / "quality_report.json",
    )

    assert report["overall_status"] == "review_recommended"
    assert any(
        check["id"] == "duration_match" and check["status"] == "warning"
        for check in report["checks"]
    )


def test_quality_report_handles_probe_failure(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("Media file not found")

    monkeypatch.setattr(quality_inspector.subprocess, "run", fake_run)

    report = quality_inspector.build_quality_report(
        tmp_path / "missing-source.mp4",
        tmp_path / "missing-audio.mp3",
        tmp_path / "missing-output.mp4",
        0,
        tmp_path / "quality_report.json",
    )

    assert report["overall_status"] == "checks_incomplete"
    assert report["warnings"]
    assert report["checks"][-1]["status"] == "incomplete"
