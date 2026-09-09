from custom_components.skolengo.colors import normalize_color


def test_none_and_empty_pass_through():
    assert normalize_color(None) is None
    assert normalize_color("") == ""


def test_already_prefixed_is_unchanged():
    assert normalize_color("#57006D") == "#57006D"


def test_bare_hex_gets_prefixed():
    assert normalize_color("57006D") == "#57006D"


def test_bare_short_hex_gets_prefixed():
    assert normalize_color("abc") == "#abc"


def test_surrounding_whitespace_is_stripped():
    assert normalize_color("  57006D  ") == "#57006D"


def test_non_hex_value_is_returned_unchanged():
    # Not a color Skolengo is documented to send, but normalize_color must
    # not crash or mangle it -- just leave whatever it can't recognize alone.
    assert normalize_color("not-a-color") == "not-a-color"
