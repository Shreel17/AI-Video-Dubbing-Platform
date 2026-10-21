import argostranslate.translate


sample_transcript = [
    {
        "start": 0.0,
        "end": 3.0,
        "text": "नमस्ते, आप कैसे हैं?",
    },
    {
        "start": 3.0,
        "end": 6.0,
        "text": "मेरा नाम राहुल है।",
    },
]


def main():
    translation = (
        argostranslate.translate.get_translation_from_codes(
            "hi",
            "en",
        )
    )

    print("Local Hindi-to-English translation test:\n")

    for segment in sample_transcript:
        translated_text = translation.translate(segment["text"])

        print(
            f"{segment['start']}s - {segment['end']}s: "
            f"{translated_text}"
        )


if __name__ == "__main__":
    main()
