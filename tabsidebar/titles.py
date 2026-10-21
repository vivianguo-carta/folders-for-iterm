"""Reads Claude Code's status out of the terminal title it sets."""

from __future__ import annotations

import re

WORKING = "working"
IDLE = "idle"

IDLE_GLYPH = "✳"
# Spinner frames: quarter-circle glyphs and the braille block some versions animate with.
WORKING_GLYPHS = re.compile(r"[◐◑◒◓⠀-⣿]")
# iTerm2 appends the running job's name, which is "node" or "claude" depending on how Claude Code runs.
JOB_SUFFIX = re.compile(r"\s+\((?:node|claude)\)$")


def parse_title(raw: str) -> tuple[str, str | None]:
    """Splits a tab title into its display text and Claude Code status (WORKING, IDLE, or None)."""
    first, rest = raw[:1], raw[1:].lstrip()
    if first == IDLE_GLYPH:
        status = IDLE
    elif first and WORKING_GLYPHS.fullmatch(first):
        status = WORKING
    else:
        return raw, None
    return JOB_SUFFIX.sub("", rest), status
