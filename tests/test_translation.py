from main import improve_hindi_translation


def test_hindi_correction_for_cant_complain():
    text = (
        "\u0908\u092e\u093e\u0928\u0926\u093e\u0930 \u0939\u094b\u0928\u0947 \u0915\u0947 "
        "\u0932\u093f\u090f \u092e\u0948\u0902 \u0936\u093f\u0915\u093e\u092f\u0924 "
        "\u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e\u0964"
    )
    result = improve_hindi_translation(text)
    assert result != text
    assert "\u0936\u093f\u0915\u093e\u092f\u0924" in result


def test_hindi_correction_for_cool():
    text = (
        "Wow, \u092f\u0939 \u0935\u093e\u0938\u094d\u0924\u0935 \u092e\u0947\u0902 "
        "\u0936\u093e\u0902\u0924 \u0932\u0917\u0924\u093e \u0939\u0948\u0964"
    )
    result = improve_hindi_translation(text)
    assert result != text
    assert "\u092c\u0922\u093c\u093f\u092f\u093e" in result


def test_hindi_correction_for_sleeping_in():
    text = "\u092e\u0948\u0902 \u0938\u094b \u0930\u0939\u093e \u0939\u0942\u0901\u0964"
    result = improve_hindi_translation(text)
    assert result != text
    assert "\u0938\u094b\u0928\u093e" in result


def test_hindi_correction_for_friendly_coworkers():
    text = (
        "\u092e\u0947\u0930\u0947 \u0938\u0939\u0915\u0930\u094d\u092e\u0940 "
        "\u0935\u093e\u0938\u094d\u0924\u0935 \u092e\u0947\u0902 "
        "\u0926\u094b\u0938\u094d\u0924\u093e\u0928\u093e \u0914\u0930 "
        "\u0938\u0939\u093e\u092f\u0915 \u0939\u094b\u0924\u0947 \u0939\u0948\u0902\u0964"
    )
    result = improve_hindi_translation(text)
    assert result != text
    assert "\u092e\u093f\u0932\u0928\u0938\u093e\u0930" in result


def test_unmatched_text_is_unchanged():
    text = "Namaste"
    assert improve_hindi_translation(text) == text



def test_hindi_correction_handles_comma_and_period():
    text = (
        "\u0908\u092e\u093e\u0928\u0926\u093e\u0930 "
        "\u0939\u094b\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f, "
        "\u092e\u0948\u0902 \u0936\u093f\u0915\u093e\u092f\u0924 "
        "\u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u093e."
    )
    result = improve_hindi_translation(text)
    assert "\u0938\u091a \u0915\u0939\u0942\u0901 \u0924\u094b" in result


def test_hindi_correction_for_sleeping_in_output_variant():
    text = (
        "\u092e\u0941\u091d\u0947 \u0930\u093e\u0924 \u092e\u0947\u0902 "
        "\u0938\u092c\u0938\u0947 \u091c\u094d\u092f\u093e\u0926\u093e "
        "\u091c\u093e\u0917\u0928\u093e \u092a\u0938\u0902\u0926 \u0939\u0948."
    )
    result = improve_hindi_translation(text)
    assert result != text


def test_hindi_correction_adds_missing_space():
    text = (
        "\u092f\u0939 \u0935\u093e\u0938\u094d\u0924\u0935 "
        "\u092e\u0947\u0902 \u090a\u0930\u094d\u091c\u093e\u0935\u093e\u0928"
        "\u0914\u0930 \u092e\u091c\u0947\u0926\u093e\u0930 "
        "\u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0939\u0948\u0964"
    )
    result = improve_hindi_translation(text)
    assert "\u090a\u0930\u094d\u091c\u093e\u0935\u093e\u0928 "
    "\u0914\u0930" in result


def test_hindi_correction_adds_space_before_shorts():
    text = (
        "\u092e\u0948\u0902 \u0917\u0930\u094d\u092e\u093f\u092f\u094b\u0902 "
        "\u092e\u0947\u0902 \u092d\u0940 "
        "\u0936\u0949\u0930\u094d\u091f\u094d\u0938\u092a\u0939\u0928 "
        "\u0938\u0915\u0924\u093e \u0939\u0942\u0902\u0964"
    )
    result = improve_hindi_translation(text)
    assert "\u0936\u0949\u0930\u094d\u091f\u094d\u0938 \u092a\u0939\u0928" in result


def test_hindi_correction_translates_wow():
    text = "Wow, \u092f\u0939 \u0924\u094b \u092c\u0939\u0941\u0924 \u092c\u0922\u093c\u093f\u092f\u093e \u0939\u0948\u0964"
    result = improve_hindi_translation(text)
    assert result.startswith("\u0935\u093e\u0939,")
