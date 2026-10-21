
import asyncio
from pathlib import Path

import edge_tts


# Project directory
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"

# Create output directory if it does not exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    text = (
        "Hello! This is an automated video dubbing system. "
        "We are testing English speech generation."
    )

    output_audio = OUTPUT_DIR / "speech_test.mp3"

    print("Generating English speech...")

    speech = edge_tts.Communicate(
        text=text,
        voice="en-US-AriaNeural",
    )

    await speech.save(str(output_audio))

    print(f"Speech generated successfully: {output_audio}")


if __name__ == "__main__":
    asyncio.run(main())