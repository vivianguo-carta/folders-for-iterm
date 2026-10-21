"""Keeps the folder tree in sync with iTerm2 and turns page commands into changes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Awaitable, Callable, Protocol

import iterm2
from websockets.exceptions import ConnectionClosed

from tabsidebar.model import DEFAULT_PALETTE, FolderStore, LiveTab
from tabsidebar.tabcolors import TabColorizer
from tabsidebar.titles import parse_title

log = logging.getLogger(__name__)

KEY_VARIABLE = "user.tabsidebar_key"


class BadCommand(ValueError):
    """A page command that is malformed or refers to something that no longer exists."""


class Client(Protocol):
    async def send_str(self, data: str) -> None: ...


class Sidebar:
    """Single writer of iTerm2 tab colors and of what the pages see.

    Every change, whether from iTerm2 or from a page, goes through `_publish`, which runs one at a time.
    """

    def __init__(
        self,
        connection: iterm2.Connection,
        app: iterm2.App,
        store: FolderStore,
        colorizer: TabColorizer | None = None,
    ) -> None:
        self.connection = connection
        self.app = app
        self.store = store
        self.colorizer = colorizer or TabColorizer(app)
        self.live: list[LiveTab] = []
        self._clients: set[Client] = set()
        self._last_payload: str | None = None
        self._keys_by_tab_id: dict[str, str] = {}
        self._titles_by_tab_id: dict[str, str] = {}
        self._title_watchers: dict[str, asyncio.Task] = {}
        self._dirty = asyncio.Event()
        self._publish_lock = asyncio.Lock()
        self._commands: dict[str, Callable[[dict], Awaitable[None]]] = {
            "activate": self._activate,
            "create_folder": self._create_folder,
            "rename_folder": self._rename_folder,
            "delete_folder": self._delete_folder,
            "move_tab": self._move_tab,
            "set_folder_color": self._set_folder_color,
            "set_color_tabs": self._set_color_tabs,
            "set_palette": self._set_palette,
            "set_custom_color": self._set_custom_color,
            "reset_custom_palette": self._reset_custom_palette,
        }

    def mark_dirty(self) -> None:
        self._dirty.set()

    async def run_refresh_loop(self) -> None:
        """Coalesces bursts of iTerm2 events into one refresh at a time."""
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self._refresh()
            except ConnectionClosed:
                raise
            except Exception:
                # Usually a tab closing mid-refresh; the layout event for that close triggers another refresh.
                log.exception("refresh failed")

    async def add_client(self, client: Client) -> None:
        self._clients.add(client)
        await self._send(client, self._payload())

    def remove_client(self, client: Client) -> None:
        self._clients.discard(client)

    async def handle_command(self, command: object) -> None:
        if not isinstance(command, dict) or command.get("action") not in self._commands:
            raise BadCommand(f"unknown command {command!r}")
        try:
            await self._commands[command["action"]](command)
        except (KeyError, ValueError, TypeError) as error:
            raise BadCommand(f"{command['action']}: {error!r}") from error
        await self._publish()

    async def resync(self, client: Client) -> None:
        """Sends the current tree to one page, e.g. after it sent a stale command."""
        await self._send(client, self._payload())

    async def _refresh(self) -> None:
        live = []
        for window in self.app.terminal_windows:
            for tab in window.tabs:
                title, status = parse_title(await self._title_for(tab))
                live.append(LiveTab(key=await self._key_for(tab), tab_id=tab.tab_id, title=title, status=status))
        self.live = live
        self.store.sync_live_tabs(live)
        self._sync_title_watchers({t.tab_id for t in live})
        await self._publish()

    async def _title_for(self, tab: iterm2.Tab) -> str:
        # After the first read, the title watcher keeps this cache current.
        if tab.tab_id not in self._titles_by_tab_id:
            self._titles_by_tab_id[tab.tab_id] = await tab.async_get_variable("title") or ""
        return self._titles_by_tab_id[tab.tab_id]

    async def _key_for(self, tab: iterm2.Tab) -> str:
        key = self._keys_by_tab_id.get(tab.tab_id)
        if key is None:
            key = await tab.async_get_variable(KEY_VARIABLE)
            if not isinstance(key, str) or not key:
                key = uuid.uuid4().hex
                await tab.async_set_variable(KEY_VARIABLE, key)
            self._keys_by_tab_id[tab.tab_id] = key
        return key

    def _sync_title_watchers(self, open_tab_ids: set[str]) -> None:
        for tab_id in self._title_watchers.keys() - open_tab_ids:
            self._title_watchers.pop(tab_id).cancel()
            self._keys_by_tab_id.pop(tab_id, None)
            self._titles_by_tab_id.pop(tab_id, None)
        for tab_id in open_tab_ids - self._title_watchers.keys():
            task = asyncio.create_task(self._watch_title(tab_id))
            task.add_done_callback(lambda t, tab_id=tab_id: self._on_watcher_done(tab_id, t))
            self._title_watchers[tab_id] = task

    async def _watch_title(self, tab_id: str) -> None:
        async with iterm2.VariableMonitor(
            self.connection, iterm2.VariableScopes.TAB, "title", tab_id
        ) as monitor:
            while True:
                self._titles_by_tab_id[tab_id] = await monitor.async_get() or ""
                self.mark_dirty()

    def _on_watcher_done(self, tab_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        log.error("title watcher for tab %s stopped", tab_id, exc_info=task.exception())
        # Forget the dead watcher and the cached title; the next refresh rereads it and starts a new watcher.
        # Not refreshing right away avoids a hot loop if the watcher keeps failing.
        if self._title_watchers.get(tab_id) is task:
            del self._title_watchers[tab_id]
            self._titles_by_tab_id.pop(tab_id, None)

    async def _publish(self) -> None:
        async with self._publish_lock:
            await self.colorizer.apply(self.store.tab_colors(self.live))
            payload = self._payload()
            if payload == self._last_payload:
                return  # e.g. a spinner frame: the title changed but what the page shows did not
            self._last_payload = payload
            for client in list(self._clients):
                await self._send(client, payload)

    def _payload(self) -> str:
        return json.dumps({
            "type": "tree",
            "folders": self.store.tree(self.live),
            "color_tabs": self.store.color_tabs,
            "palette": {
                "name": self.store.palette_name,
                "colors": list(self.store.active_palette),
                "default": list(DEFAULT_PALETTE),
                "custom": list(self.store.custom_palette),
            },
        })

    async def _send(self, client: Client, payload: str) -> None:
        try:
            await client.send_str(payload)
        except Exception as error:
            # A page that is closing raises here before its handler has removed it.
            log.info("dropping sidebar client after failed send: %r", error)
            self._clients.discard(client)

    async def _activate(self, command: dict) -> None:
        tab = self.app.get_tab_by_id(command["tab_id"])
        if tab is not None:
            await tab.async_activate(order_window_front=True)

    async def _create_folder(self, command: dict) -> None:
        self.store.create_folder(str(command["name"]))

    async def _rename_folder(self, command: dict) -> None:
        self.store.rename_folder(command["folder_id"], str(command["name"]))

    async def _delete_folder(self, command: dict) -> None:
        self.store.delete_folder(command["folder_id"])

    async def _move_tab(self, command: dict) -> None:
        if command["key"] not in {t.key for t in self.live}:
            raise KeyError(f"no open tab with key {command['key']!r}")
        self.store.move_tab(command["key"], command["folder_id"], command.get("before_key"))

    async def _set_folder_color(self, command: dict) -> None:
        self.store.set_folder_color(command["folder_id"], command["slot"])

    async def _set_color_tabs(self, command: dict) -> None:
        self.store.set_color_tabs(command["enabled"] is True)

    async def _set_palette(self, command: dict) -> None:
        self.store.set_palette(command["name"])

    async def _set_custom_color(self, command: dict) -> None:
        self.store.set_custom_color(command["slot"], command["color"])

    async def _reset_custom_palette(self, command: dict) -> None:
        self.store.reset_custom_palette()
