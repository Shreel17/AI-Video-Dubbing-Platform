
import asyncio
import math
import subprocess
import time
from pathlib import Path

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

VOICE = "en-US-AriaNeural"
WHISPER_MODEL = "base"
SAMPLE_RATE = 44100
CHUNK_SECONDS = 60


# ============================================================
# HELPER: RUN A SUBPROCESS WITH USEFUL ERROR DETAILS
# ============================================================

def run_command(command: list[str]) -> subprocess.CompletedProcess:
    """Run a command and report useful details if it fails."""

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
        "outtmpl": str(
            DOWNLOAD_DIR / "%(title).100s.%(ext)s"
        ),
        "merge_output_format": "mp4",
        "noplaylist": True,
    }

    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        video_path = Path(downloader.prepare_filename(info))

    # yt-dlp may merge separate streams into an MP4 file.
    if not video_path.exists():
        merged_path = video_path.with_suffix(".mp4")

        if merged_path.exists():
            video_path = merged_path

    if not video_path.exists():
        raise FileNotFoundError(
            "Downloaded video could not be located."
        )

    print(f"Downloaded: {video_path.name}")

    return video_path


# ============================================================
# STEP 2: TRANSCRIBE VIDEO
# ============================================================

def transcribe_video(video_path: Path):
    """Recognize speech and retain the original timestamps."""

    print("\n[2/5] Transcribing speech...")

    model = WhisperModel(
        WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
    )

    segments, info = model.transcribe(
        str(video_path),
        beam_size=5,
    )

    transcript = []

    for segment in segments:
        text = segment.text.strip()

        if text and any(character.isalnum() for character in text):
            transcript.append(
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": text,
                }
            )

    print(f"Detected language: {info.language}")
    print(f"Speech segments found: {len(transcript)}")

    if not transcript:
        raise ValueError(
            "No clear speech was detected. "
            "Please test with a video containing dialogue."
        )

    return transcript, info.language


# ============================================================
# STEP 3: TRANSLATE TRANSCRIPT INTO ENGLISH
# ============================================================

def translate_to_english(transcript, source_language: str):
    """Translate recognized speech into English using Argos."""

    if source_language == "en":
        print(
            "\n[3/5] Speech is already English; "
            "translation skipped."
        )
        return transcript

    print("\n[3/5] Translating speech into English locally...")

    import argostranslate.translate

    try:
        translation = (
            argostranslate.translate
            .get_translation_from_codes(
                source_language,
                "en",
            )
        )
    except Exception as error:
        raise RuntimeError(
            f"No usable translation model was found for "
            f"{source_language} to English. "
            "Install the required Argos Translate language model. "
            f"Details: {error}"
        ) from error

    translated_transcript = []
    total_segments = len(transcript)

    for index, item in enumerate(transcript):
        translated_text = translation.translate(
            item["text"]
        ).strip()

        if not translated_text:
            raise RuntimeError(
                f"Translation returned empty text for segment "
                f"{index + 1}/{total_segments}."
            )

        translated_transcript.append(
            {
                **item,
                "text": translated_text,
            }
        )

        if (
            (index + 1) % 10 == 0
            or index + 1 == total_segments
        ):
            print(
                f"Translated {index + 1}/"
                f"{total_segments} segments"
            )

    print("Local translation finished.")

    return translated_transcript


# ============================================================
# STEP 4: GENERATE TIMESTAMP-ALIGNED ENGLISH SPEECH
# ============================================================

async def generate_speech(
    transcript,
    output_audio: Path,
    total_duration: float,
):
    """Generate speech clips and mix them in timeline chunks."""

    if not transcript:
        raise ValueError(
            "Cannot generate speech from an empty transcript."
        )

    if total_duration <= 0:
        raise ValueError(
            "Video duration must be greater than zero."
        )

    print("\n[4/5] Generating English speech...")

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    output_audio.parent.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # STEP A: GENERATE, VALIDATE, AND REUSE SPEECH CLIPS
    # --------------------------------------------------------

    clip_paths = []
    clip_durations = []

    for index, segment in enumerate(transcript):
        clip_path = CLIPS_DIR / f"clip_{index:05d}.mp3"
        clip_duration = 0.0

        # Retry each clip up to three times.
        # Reuse an existing clip when it is valid.
        for attempt in range(3):
            try:
                if (
                    clip_path.exists()
                    and clip_path.stat().st_size > 0
                ):
                    probe = run_command(
                        [
                            "ffprobe",
                            "-v", "error",
                            "-show_entries", "format=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(clip_path),
                        ]
                    )

                    clip_duration = float(
                        probe.stdout.strip()
                    )

                    if (
                        not math.isfinite(clip_duration)
                        or clip_duration <= 0
                    ):
                        raise RuntimeError(
                            "Audio clip has invalid duration."
                        )

                else:
                    speech = edge_tts.Communicate(
                        text=segment["text"],
                        voice=VOICE,
                    )

                    await speech.save(str(clip_path))

                    if (
                        not clip_path.exists()
                        or clip_path.stat().st_size == 0
                    ):
                        raise RuntimeError(
                            "TTS returned an empty audio clip."
                        )

                    probe = run_command(
                        [
                            "ffprobe",
                            "-v", "error",
                            "-show_entries", "format=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(clip_path),
                        ]
                    )

                    clip_duration = float(
                        probe.stdout.strip()
                    )

                    if (
                        not math.isfinite(clip_duration)
                        or clip_duration <= 0
                    ):
                        raise RuntimeError(
                            "Audio clip has invalid duration."
                        )

                # The clip is valid, so stop retrying.
                break

            except Exception as error:
                # Remove an incomplete or invalid clip before retrying.
                if clip_path.exists():
                    clip_path.unlink()

                if attempt == 2:
                    raise RuntimeError(
                        f"Could not generate clip "
                        f"{index + 1}/{len(transcript)} "
                        f"after 3 attempts. "
                        f"Last error: {error}"
                    ) from error

                wait_seconds = 2 * (attempt + 1)

                print(
                    f"Clip {index + 1}: "
                    f"attempt {attempt + 1} failed. "
                    f"Retrying in {wait_seconds} seconds..."
                )

                await asyncio.sleep(wait_seconds)

        clip_paths.append(clip_path)
        clip_durations.append(clip_duration)

        if (
            (index + 1) % 10 == 0
            or index + 1 == len(transcript)
        ):
            print(
                f"Generated/reused {index + 1}/"
                f"{len(transcript)} speech clips"
            )

    # --------------------------------------------------------
    # STEP B: PREPARE SORTED CLIPS AND TRACKING VARIABLES
    # --------------------------------------------------------

    chunk_count = math.ceil(
        total_duration / CHUNK_SECONDS
    )

    chunk_paths = []

    # Keep the concat list with the test's temporary audio chunks.
    concat_list = CLIPS_DIR.parent / "audio_chunks.txt"

    # Sort clips by their original transcript start times.
    timed_clips = sorted(
        zip(transcript, clip_paths, clip_durations),
        key=lambda item: float(item[0]["start"]),
    )

    # Track the next clip to examine and clips overlapping
    # the current timeline chunk.
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

            # Step 31: Keep temporary chunks beside the test clips.
            chunk_path = (
                CLIPS_DIR.parent
                / f"dub_chunk_{chunk_index:05d}.mp3"
            )

            # Remove clips that ended before this chunk starts.
            active_clips = [
                item
                for item in active_clips
                if (
                    float(item[0]["start"]) + item[2]
                    > chunk_start
                )
            ]

            # Add clips starting before this chunk ends.
            while next_clip_index < len(timed_clips):
                candidate = timed_clips[next_clip_index]
                candidate_start = float(candidate[0]["start"])

                if candidate_start >= chunk_end:
                    break

                active_clips.append(candidate)
                next_clip_index += 1

            # Input 0 is a silent audio track for this chunk.
            command = [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-t", str(chunk_length),
                "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            ]

            filters = []
            voice_labels = []

            # Process only clips that may overlap this chunk.
            for segment, clip_path, clip_duration in active_clips:
                speech_start = float(segment["start"])
                speech_end = speech_start + clip_duration

                # Find the part of this clip inside the chunk.
                overlap_start = max(
                    speech_start,
                    chunk_start,
                )

                overlap_end = min(
                    speech_end,
                    chunk_end,
                )

                if overlap_end <= overlap_start:
                    continue

                input_index = len(voice_labels) + 1

                command.extend(
                    ["-i", str(clip_path)]
                )

                trim_start = overlap_start - speech_start
                trim_duration = overlap_end - overlap_start

                delay_ms = round(
                    (overlap_start - chunk_start) * 1000
                )

                label = f"voice{len(voice_labels)}"

                filters.append(
                    f"[{input_index}:a]"
                    f"atrim=start={trim_start:.3f}:"
                    f"duration={trim_duration:.3f},"
                    "asetpts=PTS-STARTPTS,"
                    f"aresample={SAMPLE_RATE},"
                    "aformat=channel_layouts=stereo,"
                    f"adelay={delay_ms}|{delay_ms}"
                    f"[{label}]"
                )

                voice_labels.append(f"[{label}]")

            # Mix the active speech clips over silence.
            if voice_labels:
                mix_inputs = (
                    "[0:a]" + "".join(voice_labels)
                )

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
                        "-map", "[out]",
                    ]
                )
            else:
                # Preserve silence when no clips overlap.
                command.extend(
                    ["-map", "0:a:0"]
                )

            command.extend(
                [
                    "-c:a", "libmp3lame",
                    "-q:a", "3",
                    str(chunk_path),
                ]
            )

            run_command(command)
            chunk_paths.append(chunk_path)

            print(
                f"Mixed chunk {chunk_index + 1}/{chunk_count} "
                f"({chunk_start:.0f}s–{chunk_end:.0f}s) "
                f"| Active clips: {len(active_clips)}"
            )

        # ----------------------------------------------------
        # STEP C: JOIN ALL TIMELINE CHUNKS
        # ----------------------------------------------------

        with concat_list.open(
            "w",
            encoding="utf-8",
        ) as file:
            for chunk_path in chunk_paths:
                safe_path = (
                    str(chunk_path.resolve())
                    .replace("\\", "/")
                    .replace("'", r"'\''")
                )

                file.write(
                    f"file '{safe_path}'\n"
                )

        run_command(
            [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "libmp3lame",
                "-q:a", "3",
                str(output_audio),
            ]
        )

        print(f"Generated audio: {output_audio}")

    finally:
        # Remove temporary timeline chunks and concat list.
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
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
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
):
    """Combine the original video with the generated English dub."""

    print("\n[5/5] Combining video and dubbed audio...")

    duration = get_video_duration(video_path)

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-i", str(dubbed_audio),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", "volume=2.0",
            "-t", str(duration),
            "-movflags", "+faststart",
            str(output_video),
        ]
    )

    print(f"\nDubbed video saved: {output_video}")


def run_dubbing_pipeline(
    video_url: str,
    job_id: str,
) -> Path:
    """Run the dubbing pipeline for a background job."""

    started = time.perf_counter()

    video_path = download_video(video_url)

    transcript, source_language = transcribe_video(
        video_path
    )

    transcript = translate_to_english(
        transcript,
        source_language,
    )

    video_duration = get_video_duration(video_path)

    job_output_dir = OUTPUT_DIR / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)

    dubbed_audio = job_output_dir / "dubbed_audio.mp3"
    output_video = (
        job_output_dir / f"{video_path.stem}_english_dub.mp4"
    )

    asyncio.run(
        generate_speech(
            transcript,
            dubbed_audio,
            video_duration,
        )
    )

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

    return output_video

# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    """Run the complete video dubbing pipeline."""

    started = time.perf_counter()

    video_url = input(
        "Enter the YouTube video URL: "
    ).strip()

    video_path = download_video(video_url)

    transcript, source_language = transcribe_video(
        video_path
    )

    transcript = translate_to_english(
        transcript,
        source_language,
    )

    video_duration = get_video_duration(video_path)

    dubbed_audio = OUTPUT_DIR / "dubbed_audio.mp3"

    output_video = (
        OUTPUT_DIR / f"{video_path.stem}_english_dub.mp4"
    )

    asyncio.run(
        generate_speech(
            transcript,
            dubbed_audio,
            video_duration,
        )
    )

    combine_video(
        video_path,
        dubbed_audio,
        output_video,
    )

    elapsed = time.perf_counter() - started

    print("\n" + "=" * 55)
    print("VIDEO DUBBING COMPLETED SUCCESSFULLY")
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