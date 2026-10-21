import asyncio
import math
import subprocess
import time
from pathlib import Path
from typing import Callable

import edge_tts
from faster_whisper import WhisperModel
from yt_dlp import YoutubeDL


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "outputs"
CLIPS_DIR = OUTPUT_DIR / "speech_clips"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE = "en-US-AriaNeural"

LANGUAGE_VOICES = {
    "en": "en-US-AriaNeural",
    "hi": "hi-IN-SwaraNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-EG-SalmaNeural",
    "ru": "ru-RU-SvetlanaNeural",
}

WHISPER_MODEL = "base"
SAMPLE_RATE = 44100
CHUNK_SECONDS = 60

ProgressCallback = Callable[[int, str], None]


# ============================================================
# COMMON HELPERS
# ============================================================

def normalize_language_code(language: str | None, default: str = "en") -> str:
    """Normalize language codes such as hi-IN to hi."""
    return (language or default).strip().lower().replace("_", "-").split("-")[0]


def report_progress(
    progress_callback: ProgressCallback | None,
    progress: int,
    message: str,
) -> None:
    """Report pipeline progress when a callback is provided."""
    if progress_callback is not None:
        progress_callback(progress, message)


def run_command(command: list[str]) -> subprocess.CompletedProcess:
    """Run a command and return useful details when it fails."""
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        executable = command[0]
        raise RuntimeError(
            f"Required program '{executable}' was not found. "
            "Install FFmpeg and ensure ffmpeg and ffprobe "
            "are available in your system PATH."
        ) from error
    except subprocess.CalledProcessError as error:
        details = error.stderr or str(error)
        raise RuntimeError(
            f"Command failed:\n{details[-3000:]}"
        ) from error


def validate_target_language(target_language: str | None) -> str:
    """Validate and normalize the requested target language."""
    language = normalize_language_code(target_language)

    if language not in LANGUAGE_VOICES:
        raise ValueError(
            f"Unsupported target language code: {language}. "
            f"Supported codes: {', '.join(sorted(LANGUAGE_VOICES))}"
        )

    return language


# ============================================================
# STEP 1: DOWNLOAD VIDEO
# ============================================================

def download_video(url: str) -> Path:
    """Download a YouTube video and return its local file path."""
    if not url.startswith(
        (
            "https://www.youtube.com/",
            "https://youtube.com/",
            "https://youtu.be/",
        )
    ):
        raise ValueError("Please enter a valid YouTube URL.")

    print("\n[1/5] Downloading video...")

    options = {
        "format": "bestvideo*+bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(title).100s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
    }

    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        prepared_path = Path(downloader.prepare_filename(info))

    # yt-dlp may merge the downloaded streams into an MP4 file.
    candidates = [
        prepared_path,
        prepared_path.with_suffix(".mp4"),
    ]

    video_path = next(
        (candidate for candidate in candidates if candidate.exists()),
        None,
    )

    if video_path is None:
        raise FileNotFoundError(
            "The downloaded video could not be located."
        )

    print(f"Downloaded: {video_path.name}")
    return video_path


# ============================================================
# STEP 2: TRANSCRIBE VIDEO
# ============================================================


def transcribe_video(
    video_path: Path,
    source_language: str | None = None,
):
    """Transcribe speech while preserving word-level timestamps."""
    print("\n[2/5] Transcribing speech...")

    model = WhisperModel(
        WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
    )

    options = {
        "beam_size": 5,
        "word_timestamps": True,
    }

    if source_language:
        options["language"] = normalize_language_code(source_language)

    segments, info = model.transcribe(str(video_path), **options)

    transcript = []

    for segment in segments:
        text = segment.text.strip()

        if not text or not any(character.isalnum() for character in text):
            continue

        words = segment.words or []

        if words:
            start = float(words[0].start)
            end = float(words[-1].end)
        else:
            start = float(segment.start)
            end = float(segment.end)

        if not math.isfinite(start) or not math.isfinite(end):
            continue

        if start < 0 or end <= start:
            continue

        transcript.append(
            {
                "start": start,
                "end": end,
                "text": text,
            }
        )

    detected_language = normalize_language_code(info.language)

    print(f"Detected language: {detected_language}")
    print(f"Speech segments found: {len(transcript)}")

    if not transcript:
        raise ValueError(
            "No clear speech was detected. "
            "Please use a video containing audible dialogue."
        )

    return transcript, detected_language



def improve_hindi_translation(text: str) -> str:
    """Correct selected common English-to-Hindi translation errors."""
    import re

    corrections = [
        (
            "\u0908\u092e\u093e\u0928\u0926\u093e\u0930 \u0939\u094b\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u092e\u0948\u0902 \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e",
            "\u0938\u091a \u0915\u0939\u0942\u0901 \u0924\u094b, \u092e\u0941\u091d\u0947 \u0915\u094b\u0908 \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902 \u0939\u0948",
        ),
        (
            "\u092f\u0939 \u0935\u093e\u0938\u094d\u0924\u0935 \u092e\u0947\u0902 \u0936\u093e\u0902\u0924 \u0932\u0917\u0924\u093e \u0939\u0948",
            "\u092f\u0939 \u0924\u094b \u092c\u0939\u0941\u0924 \u092c\u0922\u093c\u093f\u092f\u093e \u0932\u0917\u0924\u093e \u0939\u0948",
        ),
        (
            "\u092e\u0948\u0902 \u0938\u094b \u0930\u0939\u093e \u0939\u0942\u0901",
            "\u092e\u0941\u091d\u0947 \u0926\u0947\u0930 \u0924\u0915 \u0938\u094b\u0928\u093e \u092a\u0938\u0902\u0926 \u0939\u0948",
        ),
        (
            "\u092e\u0947\u0930\u0947 \u0938\u0939\u0915\u0930\u094d\u092e\u0940 \u0935\u093e\u0938\u094d\u0924\u0935 \u092e\u0947\u0902 \u0926\u094b\u0938\u094d\u0924\u093e\u0928\u093e \u0914\u0930 \u0938\u0939\u093e\u092f\u0915 \u0939\u094b\u0924\u0947 \u0939\u0948\u0902",
            "\u092e\u0947\u0930\u0947 \u0938\u0939\u0915\u0930\u094d\u092e\u0940 \u092c\u0939\u0941\u0924 \u092e\u093f\u0932\u0928\u0938\u093e\u0930 \u0914\u0930 \u092e\u0926\u0926\u0917\u093e\u0930 \u0939\u0948\u0902",
        ),
    ]

    # Handle punctuation and spacing variants of common Argos outputs.
    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = re.sub(r"[,.!?\u0964]+$", "", normalized).strip()

    cant_complain_variants = [
        "\u0908\u092e\u093e\u0928\u0926\u093e\u0930 \u0939\u094b\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f, \u092e\u0948\u0902 \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e",
        "\u0908\u092e\u093e\u0928\u0926\u093e\u0930 \u0939\u094b\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u092e\u0948\u0902 \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e",
    ]
    for variant in cant_complain_variants:
        if normalized.casefold() == variant.casefold():
            return "\u0938\u091a \u0915\u0939\u0942\u0901 \u0924\u094b, \u092e\u0941\u091d\u0947 \u0915\u094b\u0908 \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902 \u0939\u0948\u0964"

    sleeping_in_variant = (
        "\u092e\u0941\u091d\u0947 \u0930\u093e\u0924 \u092e\u0947\u0902 "
        "\u0938\u092c\u0938\u0947 \u091c\u094d\u092f\u093e\u0926\u093e "
        "\u091c\u093e\u0917\u0928\u093e \u092a\u0938\u0902\u0926 \u0939\u0948"
    )
    if normalized.casefold() == sleeping_in_variant.casefold():
        return (
            "\u092e\u0941\u091d\u0947 \u0938\u0941\u092c\u0939" + " " + "\u0926\u0947\u0930 "
            "\u0924\u0915 \u0938\u094b\u0928\u093e \u092a\u0938\u0902\u0926 \u0939\u0948\u0964 "
            "\u0936\u093e\u092e \u0915\u0947 \u0938\u092e\u092f \u092e\u0948\u0902 "
            "\u0938\u092c\u0938\u0947 \u091c\u093c\u094d\u092f\u093e\u0926\u093e "
            "\u0938\u0924\u0930\u094d\u0915 \u0930\u0939\u0924\u093e \u0939\u0942\u0901\u0964"
        )

    for source, replacement in corrections:
        text = re.sub(
            re.escape(source),
            lambda _: replacement,
            text,
            flags=re.IGNORECASE,
        )

    # Repair common missing-space errors in Argos Hindi output.
    text = re.sub(
        r"\u090a\u0930\u094d\u091c\u093e\u0935\u093e\u0928(?=\u0914\u0930)",
        lambda _: "\u090a\u0930\u094d\u091c\u093e\u0935\u093e\u0928 ",
        text,
    )
    text = re.sub(
        r"\u092d\u0940(?=\u0936\u0949\u0930\u094d\u091f\u094d\u0938)",
        lambda _: "\u092d\u0940 ",
        text,
    )
    text = re.sub(
        r"\u0936\u0949\u0930\u094d\u091f\u094d\u0938(?=\u092a\u0939\u0928)",
        lambda _: "\u0936\u0949\u0930\u094d\u091f\u094d\u0938 ",
        text,
    )

    text = re.sub(
        r"^\s*Wow\s*,\s*",
        "\u0935\u093e\u0939, ",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    return text

# ============================================================
# STEP 3: TRANSLATE TRANSCRIPT
# ============================================================

def translate_transcript(
    transcript,
    source_language: str,
    target_language: str,
):
    """Translate recognized speech into the requested language."""
    source_language = normalize_language_code(source_language)
    target_language = validate_target_language(target_language)

    if source_language == target_language:
        print(
            f"Source and target are both {target_language}; "
            "translation skipped."
        )
        return transcript

    print(
        f"\n[3/5] Translating speech from "
        f"{source_language} to {target_language}..."
    )

    
    try:
        import argostranslate.translate

        # Verify that the requested language pair is installed.
        installed_languages = (
            argostranslate.translate.get_installed_languages()
        )
        source_lang = next(
            (
                lang
                for lang in installed_languages
                if lang.code == source_language
            ),
            None,
        )

        if source_lang is None:
            raise RuntimeError(
                f"Source language '{source_language}' is not installed."
            )

        target_lang = next(
            (
                lang
                for lang in installed_languages
                if lang.code == target_language
            ),
            None,
        )

        if target_lang is None:
            raise RuntimeError(
                f"Target language '{target_language}' is not installed."
            )

        translation = source_lang.get_translation(target_lang)

        if translation is None:
            raise RuntimeError(
                f"No translation model found for "
                f"{source_language} to {target_language}."
            )

    except Exception as error:
        raise RuntimeError(
            f"Argos Translate failed for "
            f"{source_language} to {target_language}. "
            f"Details: {error}"
        ) from error


    translated_transcript = []

    for index, item in enumerate(transcript, start=1):
        try:
            translated_text = translation.translate(item["text"]).strip()

            if target_language == "hi":
               translated_text = improve_hindi_translation(translated_text)
        except Exception as error:
            raise RuntimeError(
                f"Translation failed for speech segment {index}: {error}"
            ) from error

        if not translated_text:
            raise RuntimeError(
                f"Translation returned empty text for segment {index}."
            )

        translated_transcript.append(
            {
                **item,
                "text": translated_text,
            }
        )

    print(
        f"Translation finished: {source_language} "
        f"to {target_language}."
    )

    return translated_transcript


def translate_to_english(transcript, source_language: str):
    """Compatibility helper for existing English-only callers."""
    return translate_transcript(transcript, source_language, "en")


# ============================================================
# STEP 4: GENERATE TIMESTAMP-ALIGNED SPEECH
# ============================================================

async def generate_speech(
    transcript,
    output_audio: Path,
    total_duration: float,
    target_language: str = "en",
    clips_dir: Path | None = None,
):
    """
    Generate translated speech and place clips at their original
    timestamps on a silent audio timeline.
    """
    if not transcript:
        raise ValueError("Cannot generate speech from an empty transcript.")

    if not math.isfinite(total_duration) or total_duration <= 0:
        raise ValueError("Video duration must be greater than zero.")

    target_language = validate_target_language(target_language)
    voice = LANGUAGE_VOICES[target_language]

    if clips_dir is None:
        clips_dir = CLIPS_DIR

    clips_dir.mkdir(parents=True, exist_ok=True)
    output_audio.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"\n[4/5] Generating {target_language} speech "
        f"using {voice}..."
    )

    clip_paths = []
    clip_durations = []

    # Generate and validate every speech clip.
    for index, segment in enumerate(transcript):
        clip_path = (
            clips_dir
            / f"clip_{index:05d}_{target_language}.mp3"
        )

        start = float(segment["start"])

        if not math.isfinite(start) or start < 0:
            raise ValueError(
                f"Invalid start timestamp for segment {index + 1}."
            )

        clip_duration = 0.0

        for attempt in range(3):
            try:
                # Reuse only clips within this job's dedicated folder.
                if clip_path.exists() and clip_path.stat().st_size > 0:
                    probe = run_command(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(clip_path),
                        ]
                    )

                    clip_duration = float(probe.stdout.strip())

                    if (
                        not math.isfinite(clip_duration)
                        or clip_duration <= 0
                    ):
                        raise RuntimeError(
                            "Cached audio clip has an invalid duration."
                        )
                else:
                    speech = edge_tts.Communicate(
                        text=segment["text"],
                        voice=voice,
                    )

                    await speech.save(str(clip_path))

                    if (
                        not clip_path.exists()
                        or clip_path.stat().st_size == 0
                    ):
                        raise RuntimeError(
                            "Text-to-speech returned an empty audio clip."
                        )

                    probe = run_command(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(clip_path),
                        ]
                    )

                    clip_duration = float(probe.stdout.strip())

                    if (
                        not math.isfinite(clip_duration)
                        or clip_duration <= 0
                    ):
                        raise RuntimeError(
                            "Generated audio clip has an invalid duration."
                        )

                break

            except Exception as error:
                if clip_path.exists():
                    clip_path.unlink()

                if attempt == 2:
                    raise RuntimeError(
                        f"Could not generate clip {index + 1}/"
                        f"{len(transcript)} after 3 attempts. "
                        f"Last error: {error}"
                    ) from error

                wait_seconds = 2 * (attempt + 1)

                print(
                    f"Clip {index + 1}: attempt {attempt + 1} failed. "
                    f"Retrying in {wait_seconds} seconds..."
                )

                await asyncio.sleep(wait_seconds)

        clip_paths.append(clip_path)
        clip_durations.append(clip_duration)

        if (index + 1) % 10 == 0 or index + 1 == len(transcript):
            print(
                f"Generated/reused {index + 1}/"
                f"{len(transcript)} speech clips"
            )

    # Keep temporary files inside the current job's folder.
    chunk_count = math.ceil(total_duration / CHUNK_SECONDS)
    chunk_paths = []
    concat_list = clips_dir / f"audio_chunks_{target_language}.txt"

    timed_clips = sorted(
        zip(transcript, clip_paths, clip_durations),
        key=lambda item: float(item[0]["start"]),
    )

    # Estimate the speaking time available before the next segment begins.
    adjusted_clips = []
    for index, (segment, clip_path, clip_duration) in enumerate(timed_clips):
        speech_start = float(segment["start"])

        if index + 1 < len(timed_clips):
            next_start = float(timed_clips[index + 1][0]["start"])
            available_time = max(0.1, next_start - speech_start)
        else:
            available_time = clip_duration

        # Speed up only when necessary, by no more than 25%.
        playback_speed = min(
            1.25,
            max(1.0, clip_duration / available_time),
        )
        adjusted_duration = clip_duration / playback_speed

        adjusted_clips.append(
            (
                segment,
                clip_path,
                clip_duration,
                playback_speed,
                adjusted_duration,
            )
        )

    timed_clips = adjusted_clips

    next_clip_index = 0
    active_clips = []

    try:
        for chunk_index in range(chunk_count):
            chunk_start = chunk_index * CHUNK_SECONDS

            chunk_length = min(
                CHUNK_SECONDS,
                total_duration - chunk_start,
            )

            chunk_end = chunk_start + chunk_length

            chunk_path = (
                clips_dir
                / f"dub_{target_language}_chunk_{chunk_index:05d}.mp3"
            )

            # Keep clips that overlap the current chunk.
            active_clips = [
                item
                for item in active_clips
                if float(item[0]["start"]) + item[4] > chunk_start
            ]

            while next_clip_index < len(timed_clips):
                candidate = timed_clips[next_clip_index]

                if float(candidate[0]["start"]) >= chunk_end:
                    break

                active_clips.append(candidate)
                next_clip_index += 1

            # Begin with silence so speech stays at its original time.
            command = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-t",
                str(chunk_length),
                "-i",
                f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            ]

            filters = []
            voice_labels = []

            for (
                segment,
                clip_path,
                clip_duration,
                playback_speed,
                adjusted_duration,
            ) in active_clips:
                speech_start = float(segment["start"])
                speech_end = speech_start + adjusted_duration

                # Ignore clips that fall outside the video duration.
                if speech_start >= total_duration:
                    continue

                overlap_start = max(speech_start, chunk_start)
                overlap_end = min(speech_end, chunk_end, total_duration)

                if overlap_end <= overlap_start:
                    continue

                input_index = len(voice_labels) + 1
                command.extend(["-i", str(clip_path)])

                trim_start = (
                    overlap_start - speech_start
                ) * playback_speed

                trim_duration = (
                    overlap_end - overlap_start
                ) * playback_speed
                delay_ms = round(
                    (overlap_start - chunk_start) * 1000
                )

                label = f"voice{len(voice_labels)}"

                speed_filter = (
                    f"atempo={playback_speed:.5f},"
                    if playback_speed > 1.00001
                    else ""
                )

                filters.append(
                    f"[{input_index}:a]"
                    f"{speed_filter}"
                    f"atrim=start={trim_start:.3f}:"
                    f"duration={trim_duration:.3f},"
                    "asetpts=PTS-STARTPTS,"
                    f"aresample={SAMPLE_RATE},"
                    "aformat=channel_layouts=stereo,"
                    f"adelay={delay_ms}|{delay_ms}"
                    f"[{label}]"
                )

                voice_labels.append(f"[{label}]")

            if voice_labels:
                mix_inputs = "[0:a]" + "".join(voice_labels)

                filters.append(
                    f"{mix_inputs}"
                    f"amix=inputs={len(voice_labels) + 1}:"
                    "duration=first:normalize=0,"
                    "alimiter=limit=0.95[out]"
                )

                command.extend(
                    [
                        "-filter_complex",
                        ";".join(filters),
                        "-map",
                        "[out]",
                    ]
                )
            else:
                command.extend(["-map", "0:a:0"])

            command.extend(
                [
                    "-t",
                    str(chunk_length),
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "3",
                    str(chunk_path),
                ]
            )

            run_command(command)
            chunk_paths.append(chunk_path)

            print(
                f"Mixed chunk {chunk_index + 1}/{chunk_count} "
                f"({chunk_start:.0f}s–{chunk_end:.0f}s)"
            )

        # Join chunks into one continuous dubbed audio track.
        with concat_list.open("w", encoding="utf-8") as file:
            for chunk_path in chunk_paths:
                safe_path = (
                    str(chunk_path.resolve())
                    .replace("\\", "/")
                    .replace("'", r"'\''")
                )

                file.write(f"file '{safe_path}'\n")

        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "3",
                str(output_audio),
            ]
        )

        print(f"Generated audio: {output_audio}")

    finally:
        for chunk_path in chunk_paths:
            if chunk_path.exists():
                chunk_path.unlink()

        if concat_list.exists():
            concat_list.unlink()


# ============================================================
# HELPER: GET VIDEO DURATION
# ============================================================

def get_video_duration(video_path: Path) -> float:
    """Return the original video's duration in seconds."""
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )

    try:
        duration = float(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError(
            "Could not determine the video's duration."
        ) from error

    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(
            "The video duration must be positive and finite."
        )

    return duration


# ============================================================
# STEP 5: COMBINE VIDEO AND DUBBED AUDIO
# ============================================================

def combine_video(
    video_path: Path,
    dubbed_audio: Path,
    output_video: Path,
) -> None:
    """Combine the original video stream with the dubbed audio."""
    print("\n[5/5] Combining video and dubbed audio...")

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not dubbed_audio.exists() or dubbed_audio.stat().st_size == 0:
        raise FileNotFoundError(
            f"Dubbed audio file is missing or empty: {dubbed_audio}"
        )

    duration = get_video_duration(video_path)
    output_video.parent.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(dubbed_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            str(output_video),
        ]
    )

    print(f"\nDubbed video saved: {output_video}")


# ============================================================
# BACKGROUND JOB PIPELINE
# ============================================================

def run_dubbing_pipeline(
    video_url: str,
    job_id: str,
    progress_callback: ProgressCallback | None = None,
    target_language: str = "en",
    source_language: str | None = None,
) -> Path:
    """
    Run the dubbing pipeline.

    progress_callback remains the third parameter for compatibility
    with existing callers. The worker can pass target_language and
    source_language as keyword arguments.
    """
    started = time.perf_counter()
    target_language = validate_target_language(target_language)

    def report(progress: int, message: str) -> None:
        report_progress(progress_callback, progress, message)

    report(5, "Downloading video.")
    video_path = download_video(video_url)

    report(20, "Video downloaded. Transcribing speech.")

    transcript, detected_language = transcribe_video(
        video_path,
        source_language=source_language,
    )

    report(40, "Transcription completed. Translating speech.")

    transcript = translate_transcript(
        transcript,
        detected_language,
        target_language,
    )

    video_duration = get_video_duration(video_path)

    # Use a separate folder for every job to prevent stale clip reuse.
    job_output_dir = OUTPUT_DIR / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)

    clips_dir = job_output_dir / "speech_clips"

    dubbed_audio = (
        job_output_dir / f"dubbed_audio_{target_language}.mp3"
    )

    output_video = (
        job_output_dir
        / f"{video_path.stem}_{target_language}_dub.mp4"
    )

    report(55, f"Generating {target_language} speech.")

    asyncio.run(
        generate_speech(
            transcript,
            dubbed_audio,
            video_duration,
            target_language=target_language,
            clips_dir=clips_dir,
        )
    )

    report(80, "Speech generated. Combining final video.")

    combine_video(
        video_path,
        dubbed_audio,
        output_video,
    )

    elapsed = time.perf_counter() - started

    print(
        f"Job {job_id} completed in "
        f"{elapsed / 60:.2f} minutes."
    )

    report(100, "Dubbing completed successfully.")

    return output_video


# ============================================================
# STANDALONE EXECUTION
# ============================================================

def main() -> None:
    """Run the dubbing pipeline directly from the terminal."""
    started = time.perf_counter()

    video_url = input(
        "Enter the YouTube video URL: "
    ).strip()

    target_language = validate_target_language(
        input(
            "Enter target language code (en, hi, es, fr, etc.) [en]: "
        ).strip()
        or "en"
    )

    video_path = download_video(video_url)

    transcript, source_language = transcribe_video(video_path)

    transcript = translate_transcript(
        transcript,
        source_language,
        target_language,
    )

    video_duration = get_video_duration(video_path)

    standalone_dir = OUTPUT_DIR / "standalone"
    standalone_dir.mkdir(parents=True, exist_ok=True)

    clips_dir = standalone_dir / "speech_clips"

    dubbed_audio = (
        standalone_dir / f"dubbed_audio_{target_language}.mp3"
    )

    output_video = (
        standalone_dir
        / f"{video_path.stem}_{target_language}_dub.mp4"
    )

    asyncio.run(
        generate_speech(
            transcript,
            dubbed_audio,
            video_duration,
            target_language=target_language,
            clips_dir=clips_dir,
        )
    )

    combine_video(
        video_path,
        dubbed_audio,
        output_video,
    )

    elapsed = time.perf_counter() - started

    print("\n" + "=" * 55)
    print("VIDEO DUBBING COMPLETED")
    print("=" * 55)
    print(f"Original video : {video_path}")
    print(f"Dubbed audio   : {dubbed_audio}")
    print(f"Dubbed video   : {output_video}")
    print(f"Processing time: {elapsed / 60:.2f} minutes")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by the user.")
    except Exception as error:
        print(f"\nERROR: {error}")
