"""Stand-ins for the parts of iTerm2 that Sidebar and the server touch."""

from __future__ import annotations

import asyncio
import json

from tabsidebar.sidebar import Sidebar


class FakeTab:
    def __init__(self, tab_id: str, title: str) -> None:
        self.tab_id = tab_id
        self.variables = {"title": title}
        self.sessions: list = []
        self.activated = False
        self.fail_next_read = False

    async def async_get_variable(self, name: str):
        if self.fail_next_read:
            self.fail_next_read = False
            raise RuntimeError("tab closed mid-refresh")
        return self.variables.get(name)

    async def async_set_variable(self, name: str, value) -> None:
        self.variables[name] = value

    async def async_activate(self, order_window_front: bool = True) -> None:
        self.activated = True


class FakeWindow:
    def __init__(self, tabs: list[FakeTab]) -> None:
        self.tabs = tabs


class FakeApp:
    def __init__(self, *tabs: FakeTab) -> None:
        self.terminal_windows = [FakeWindow(list(tabs))]

    def get_tab_by_id(self, tab_id: str):
        return next((t for w in self.terminal_windows for t in w.tabs if t.tab_id == tab_id), None)


class FakeColorizer:
    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0

    async def apply(self, wanted) -> None:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1


class RecordingClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict] = []

    async def send_str(self, data: str) -> None:
        if self.fail:
            raise ConnectionResetError("Cannot write to closing transport")
        self.messages.append(json.loads(data))


class SidebarWithoutWatchers(Sidebar):
    """A Sidebar whose title watchers just idle, since there is no iTerm2 connection to subscribe to."""

    async def _watch_title(self, tab_id: str) -> None:
        await asyncio.Event().wait()
