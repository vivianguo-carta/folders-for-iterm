import asyncio
import json
from types import SimpleNamespace

import iterm2
import pytest

from tabsidebar.tabcolors import ORIGINAL_VARIABLE, TabColorizer

VARIANTS = {"": "", "_light": " (Light)", "_dark": " (Dark)"}


def decode_color(raw: str) -> iterm2.Color:
    color = iterm2.Color()
    color.from_dict(json.loads(raw))
    return color


class FakeSession:
    """Holds profile properties the way iTerm2 reports them back, keyed by profile key."""

    def __init__(self, session_id: str, use: bool = False, color: str | None = None) -> None:
        self.session_id = session_id
        self.variables: dict = {}
        self.profile: dict[str, str] = {}
        for suffix in VARIANTS.values():
            self.profile[f"Use Tab Color{suffix}"] = json.dumps(use)
            if color:
                self.profile[f"Tab Color{suffix}"] = json.dumps(iterm2.Color.from_hex(color).get_dict())
        self.profile_writes = 0
        self.variable_reads = 0

    async def async_get_profile(self):
        attrs = {}
        for variant, suffix in VARIANTS.items():
            raw = self.profile.get(f"Tab Color{suffix}")
            attrs[f"tab_color{variant}"] = decode_color(raw) if raw else None
            attrs[f"use_tab_color{variant}"] = json.loads(self.profile[f"Use Tab Color{suffix}"])
        return SimpleNamespace(**attrs)

    async def async_set_profile_properties(self, update: iterm2.LocalWriteOnlyProfile) -> None:
        self.profile.update(update.values)
        self.profile_writes += 1

    async def async_get_variable(self, name: str):
        self.variable_reads += 1
        return json.loads(self.variables.get(name, "null"))

    async def async_set_variable(self, name: str, value) -> None:
        # The real API JSON-encodes the value, so a fake that stored objects could hide unserializable ones.
        self.variables[name] = json.dumps(value)

    def tab_colors(self, expected: tuple[bool, str | None]) -> bool:
        return all(self.tab_color(suffix) == expected for suffix in VARIANTS.values())

    def tab_color(self, suffix: str = "") -> tuple[bool, str | None]:
        raw = self.profile.get(f"Tab Color{suffix}")
        hex_color = decode_color(raw).hex if raw else None
        return json.loads(self.profile[f"Use Tab Color{suffix}"]), hex_color


class FakeApp:
    def __init__(self, tabs: dict[str, list[FakeSession]]) -> None:
        self.tabs = tabs

    def get_tab_by_id(self, tab_id: str):
        sessions = self.tabs.get(tab_id)
        return SimpleNamespace(sessions=sessions) if sessions is not None else None


def run(coro):
    return asyncio.run(coro)


def test_painting_colors_every_pane_in_light_and_dark_variants():
    left, right = FakeSession("s1"), FakeSession("s2")
    colorizer = TabColorizer(FakeApp({"t1": [left, right]}))

    run(colorizer.apply({"t1": "#3b82f6"}))

    for session in (left, right):
        for suffix in VARIANTS.values():
            assert session.tab_color(suffix) == (True, "#3b82f6")


def test_uncoloring_restores_the_tabs_own_color():
    session = FakeSession("s1", use=True, color="#e5534b")
    colorizer = TabColorizer(FakeApp({"t1": [session]}))

    run(colorizer.apply({"t1": "#3b82f6"}))
    run(colorizer.apply({"t1": None}))

    assert session.tab_colors((True, "#e5534b"))


def test_uncoloring_a_tab_that_had_no_color_turns_tab_color_off():
    session = FakeSession("s1")
    colorizer = TabColorizer(FakeApp({"t1": [session]}))

    run(colorizer.apply({"t1": "#3b82f6"}))
    run(colorizer.apply({"t1": None}))

    assert all(not session.tab_color(suffix)[0] for suffix in VARIANTS.values())


def test_repainting_keeps_the_first_original_not_the_folder_color():
    session = FakeSession("s1", use=True, color="#e5534b")
    colorizer = TabColorizer(FakeApp({"t1": [session]}))

    run(colorizer.apply({"t1": "#3b82f6"}))
    run(colorizer.apply({"t1": "#46a758"}))
    run(colorizer.apply({"t1": None}))

    assert session.tab_colors((True, "#e5534b"))


def test_tab_painted_by_a_previous_run_is_restored_after_restart():
    session = FakeSession("s1", use=True, color="#e5534b")
    run(TabColorizer(FakeApp({"t1": [session]})).apply({"t1": "#3b82f6"}))

    run(TabColorizer(FakeApp({"t1": [session]})).apply({"t1": None}))

    assert session.tab_colors((True, "#e5534b"))


def test_unchanged_colors_do_not_query_or_rewrite_iterm_on_each_refresh():
    painted, plain = FakeSession("s1"), FakeSession("s2")
    colorizer = TabColorizer(FakeApp({"t1": [painted], "t2": [plain]}))
    run(colorizer.apply({"t1": "#3b82f6", "t2": None}))
    reads_after_first_pass = (painted.variable_reads, plain.variable_reads)

    run(colorizer.apply({"t1": "#3b82f6", "t2": None}))

    assert (painted.profile_writes, plain.profile_writes) == (1, 0)
    assert (painted.variable_reads, plain.variable_reads) == reads_after_first_pass


@pytest.mark.parametrize("junk", ["a string", {"use": "yes"}, {**{f"use{v}": True for v in ("", "_light", "_dark")}, "color": "red"}])
def test_malformed_saved_original_is_discarded_instead_of_crashing(junk):
    # Terminal output can set this variable (OSC 1337 SetUserVar), so it cannot be trusted.
    session = FakeSession("s1", use=True, color="#e5534b")
    run(session.async_set_variable(ORIGINAL_VARIABLE, junk))
    colorizer = TabColorizer(FakeApp({"t1": [session]}))

    run(colorizer.apply({"t1": None}))
    run(colorizer.apply({"t1": "#3b82f6"}))
    run(colorizer.apply({"t1": None}))

    assert session.tab_colors((True, "#e5534b"))


def test_sessions_of_closed_tabs_are_forgotten():
    session = FakeSession("s1")
    app = FakeApp({"t1": [session]})
    colorizer = TabColorizer(app)
    run(colorizer.apply({"t1": "#3b82f6"}))

    del app.tabs["t1"]
    run(colorizer.apply({}))

    assert colorizer._known == {}


def test_wide_gamut_original_colors_are_kept_and_restored_exactly():
    # iTerm2 saves Display P3 colors as "p3#rrggbb"; treating those as malformed would lose the tab's own color.
    session = FakeSession("s1")
    run(session.async_set_variable(ORIGINAL_VARIABLE, {
        "use": False, "color": None,
        "use_light": False, "color_light": None,
        "use_dark": True, "color_dark": "p3#eddd68",
    }))
    colorizer = TabColorizer(FakeApp({"t1": [session]}))

    run(colorizer.apply({"t1": "#3b82f6"}))
    run(colorizer.apply({"t1": None}))

    use_dark = json.loads(session.profile["Use Tab Color (Dark)"])
    assert (use_dark, decode_color(session.profile["Tab Color (Dark)"]).hex) == (True, "p3#eddd68")
