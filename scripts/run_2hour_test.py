
import asyncio
import time
from pathlib import Path
import main as dubbing


def run_2_hour_test():
    video_path = Path("downloads/2_hour_test.mp4")

    if not video_path.exists():
        raise FileNotFoundError(f"Source video not found: {video_path}")

    test_dir = Path("outputs/2_hour_test")
    test_dir.mkdir(parents=True, exist_ok=True)

    dubbing.CLIPS_DIR = test_dir / "speech_clips"
    dubbing.CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    dubbed_audio = test_dir / "dubbed_audio.mp3"
    output_video = test_dir / "2_hour_test_english_dub.mp4"

    started = time.perf_counter()

    print("=" * 55)
    print("2-HOUR VIDEO DUBBING TEST")
    print("=" * 55)
    print(f"Source: {video_path}")
    print(f"Output folder: {test_dir.resolve()}")

    transcript, source_language = dubbing.transcribe_video(video_path)
    transcript = dubbing.translate_to_english(transcript, source_language)

    duration = dubbing.get_video_duration(video_path)

    asyncio.run(
        dubbing.generate_speech(transcript, dubbed_audio, duration)
    )

    dubbing.combine_video(video_path, dubbed_audio, output_video)

    elapsed = time.perf_counter() - started

    print("\n" + "=" * 55)
    print("2-HOUR TEST COMPLETED")
    print("=" * 55)
    print(f"Source video: {video_path.resolve()}")
    print(f"Dubbed audio: {dubbed_audio.resolve()}")
    print(f"Dubbed video: {output_video.resolve()}")
    print(f"Processing time: {elapsed / 60:.2f} minutes")


if __name__ == "__main__":
    try:
        run_2_hour_test()
    except KeyboardInterrupt:
        print("\nTest interrupted by the user.")
    except Exception as error:
        print(f"\nERROR: {error}")
        raise