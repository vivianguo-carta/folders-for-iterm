"""Paints iTerm2 tabs with their folder's color and restores their own color afterwards."""

from __future__ import annotations

import logging
import re

import iterm2

log = logging.getLogger(__name__)

ORIGINAL_VARIABLE = "user.tabsidebar_original_tab_color"
# Profiles can use one tab color, or separate ones for light and dark mode; paint and restore all three.
# iTerm2 writes wide-gamut colors as "p3#rrggbb"; Color.from_hex reads both forms back exactly.
SAVED_COLOR = re.compile(r"(?:p3)?#[0-9a-fA-F]{6}")
VARIANTS = ("", "_light", "_dark")


class TabColorizer:
    """Not safe to run concurrently with itself: callers serialize `apply`."""

    def __init__(self, app: iterm2.App) -> None:
        self.app = app
        # Per session: the folder color this run painted, or None once it is known to carry no saved original.
        self._known: dict[str, str | None] = {}

    async def apply(self, wanted_by_tab_id: dict[str, str | None]) -> None:
        """Makes each tab's sessions match `wanted_by_tab_id`: a hex color, or None for the tab's own color."""
        open_sessions: set[str] = set()
        for tab_id, color in wanted_by_tab_id.items():
            tab = self.app.get_tab_by_id(tab_id)
            if tab is None:
                continue
            for session in tab.sessions:
                open_sessions.add(session.session_id)
                await self._apply_to_session(session, color)
        for session_id in self._known.keys() - open_sessions:
            del self._known[session_id]

    async def _apply_to_session(self, session: iterm2.Session, color: str | None) -> None:
        session_id = session.session_id
        if session_id in self._known and self._known[session_id] == color:
            return
        original = await _saved_original(session)
        if color is not None:
            await self._paint(session, color, original)
        elif original is not None:
            await self._restore(session, original)
        self._known[session_id] = color

    async def _paint(self, session: iterm2.Session, color: str, original: dict | None) -> None:
        if original is None:
            profile = await session.async_get_profile()
            original = {}
            for variant in VARIANTS:
                saved_color = getattr(profile, f"tab_color{variant}")
                original[f"use{variant}"] = bool(getattr(profile, f"use_tab_color{variant}"))
                original[f"color{variant}"] = saved_color.hex if saved_color else None
            await session.async_set_variable(ORIGINAL_VARIABLE, original)
        update = iterm2.LocalWriteOnlyProfile()
        for variant in VARIANTS:
            getattr(update, f"set_tab_color{variant}")(iterm2.Color.from_hex(color))
            getattr(update, f"set_use_tab_color{variant}")(True)
        await session.async_set_profile_properties(update)

    async def _restore(self, session: iterm2.Session, original: dict) -> None:
        update = iterm2.LocalWriteOnlyProfile()
        for variant in VARIANTS:
            if original[f"color{variant}"] is not None:
                getattr(update, f"set_tab_color{variant}")(iterm2.Color.from_hex(original[f"color{variant}"]))
            getattr(update, f"set_use_tab_color{variant}")(original[f"use{variant}"])
        await session.async_set_profile_properties(update)
        await session.async_set_variable(ORIGINAL_VARIABLE, None)


async def _saved_original(session: iterm2.Session) -> dict | None:
    """The session's saved original colors, or None; anything malformed is discarded.

    Terminal output can set user variables (OSC 1337 SetUserVar), so the value is untrusted.
    """
    raw = await session.async_get_variable(ORIGINAL_VARIABLE)
    if not raw:
        return None
    if _is_valid_original(raw):
        return raw
    log.warning("discarding malformed %s on session %s: %r", ORIGINAL_VARIABLE, session.session_id, raw)
    await session.async_set_variable(ORIGINAL_VARIABLE, None)
    return None


def _is_valid_original(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    for variant in VARIANTS:
        color = raw.get(f"color{variant}")
        if not isinstance(raw.get(f"use{variant}"), bool):
            return False
        if color is not None and not (isinstance(color, str) and SAVED_COLOR.fullmatch(color)):
            return False
    return True
