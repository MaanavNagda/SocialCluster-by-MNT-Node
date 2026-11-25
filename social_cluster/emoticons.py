"""Shared typed-emoticon to emoji mapping and replacement helpers."""

EMOTICON_MAP = {
    ":-)": "🙂",
    ":)": "🙂",
    ":-(": "🙁",
    ":(": "🙁",
    ":-D": "😃",
    ":D": "😃",
    ";-)": "😉",
    ";)": "😉",
    ":-P": "😛",
    ":P": "😛",
    ":-p": "😛",
    ":p": "😛",
    ":-O": "😮",
    ":O": "😮",
    ":-o": "😮",
    ":o": "😮",
    ":-/": "😕",
    ":/": "😕",
    ":'-)": "😂",
    ":')": "😂",
    ":'(": "😢",
    "</3": "💔",
    "<3": "❤️",
    "XD": "😆",
    "xD": "😆",
}

_EMOTICONS_BY_LENGTH = sorted(EMOTICON_MAP, key=len, reverse=True)


def _utf16_units(char):
    return 2 if ord(char) > 0xFFFF else 1


def python_index_for_utf16_offset(text, utf16_offset):
    """Convert a Qt UTF-16 text offset to a Python string index.

    Qt widget cursor and selection positions count UTF-16 code units, while
    Python string indices count Unicode code points. The two differ after
    astral characters such as most emoji.
    """
    if not isinstance(utf16_offset, int) or utf16_offset < 0:
        return None
    if utf16_offset == 0:
        return 0
    units = 0
    for index, char in enumerate(text):
        units += _utf16_units(char)
        if units == utf16_offset:
            return index + 1
        if units > utf16_offset:
            return None
    return None


def utf16_offset_for_python_index(text, python_index):
    """Convert a Python string index to a Qt UTF-16 text offset."""
    if not isinstance(python_index, int):
        return None
    if python_index < 0 or python_index > len(text):
        return None
    return sum(_utf16_units(char) for char in text[:python_index])


def _is_word_char(char):
    return char == "_" or char.isalnum()


def match_emoticon_at_end(text):
    """Return ``(emoticon, emoji)`` when text ends with a known emoticon."""
    if not text:
        return None
    for emoticon in _EMOTICONS_BY_LENGTH:
        if text.endswith(emoticon):
            return emoticon, EMOTICON_MAP[emoticon]
    return None


def find_emoticon_replacement(text, cursor_position):
    """Return replacement bounds for an emoticon immediately before the cursor.

    The return value is ``(start, end, emoticon, emoji)``, where replacing
    ``text[start:end]`` with ``emoji`` performs the conversion. ``None`` is
    returned when the cursor is invalid, is not immediately after a known
    emoticon, or the emoticon is embedded in a word (for example a URL).
    """
    if not isinstance(cursor_position, int):
        return None
    if cursor_position < 0 or cursor_position > len(text):
        return None
    match = match_emoticon_at_end(text[:cursor_position])
    if match is None:
        return None
    emoticon, emoji = match
    start = cursor_position - len(emoticon)
    if start > 0 and _is_word_char(text[start - 1]):
        return None
    return start, cursor_position, emoticon, emoji
