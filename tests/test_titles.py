import pytest

from tabsidebar.titles import IDLE, WORKING, parse_title


def test_idle_claude_title_loses_glyph_and_node_suffix():
    assert parse_title("✳ SIB-1919 PR throughput tips (node)") == ("SIB-1919 PR throughput tips", IDLE)


@pytest.mark.parametrize("frame", ["◐", "◑", "◒", "◓", "⠂", "⠐"])
def test_every_spinner_frame_reads_as_working(frame):
    assert parse_title(f"{frame} iTerm2 tab grouping app (node)") == ("iTerm2 tab grouping app", WORKING)


@pytest.mark.parametrize("title", ["-zsh", "** au exemptions metal", "COSEC DEPLOY", "vim (node)", ""])
def test_non_claude_titles_are_left_exactly_as_is(title):
    assert parse_title(title) == (title, None)


def test_parenthesised_text_that_is_not_the_job_name_is_kept():
    assert parse_title("✳ Fix login (staging)") == ("Fix login (staging)", IDLE)
