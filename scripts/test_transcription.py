from pathlib import Path
from faster_whisper import WhisperModel


# Project directory
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "downloads"

# Find downloaded MP4 videos
video_files = list(VIDEO_DIR.glob("*.mp4"))

if not video_files:
    raise FileNotFoundError(
        "No MP4 video found in the downloads folder."
    )

# Select the first available video
video_path = video_files[0]

print(f"Video: {video_path.name}")
print("Loading speech recognition model...")

# CPU mode is compatible with most Windows computers
model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8",
)

print("Transcribing speech. The first run may download the model...")

# Transcribe the video
segments, info = model.transcribe(
    str(video_path),
    beam_size=5,
)

print(f"Detected language: {info.language}")
print("\n--- TRANSCRIPT ---")

segment_count = 0

for segment in segments:
    print(
        f"[{segment.start:.2f}s - {segment.end:.2f}s] "
        f"{segment.text.strip()}"
    )
    segment_count += 1

print(
    f"\nTranscription complete. Segments found: {segment_count}"
)