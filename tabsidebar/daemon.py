"""Starts the sidebar: connects to iTerm2, serves the Toolbelt page, and exits when iTerm2 goes away."""

from __future__ import annotations

import argparse
import asyncio
import errno
import logging
import os
import secrets
from pathlib import Path

import iterm2
from aiohttp import web

from tabsidebar import agent
from tabsidebar.model import FolderStore
from tabsidebar.server import build_web_app, page_version
from tabsidebar.sidebar import Sidebar
from tabsidebar.toolbelt import register_toolbelt_tool

log = logging.getLogger("tabsidebar")

HOST = "127.0.0.1"
PORT = int(os.environ.get("TABSIDEBAR_PORT", "47821"))
ORIGIN = f"http://{HOST}:{PORT}"
SUPPORT_DIR = Path.home() / "Library/Application Support/tabsidebar"
STATE_PATH = SUPPORT_DIR / "state.json"
TOKEN_PATH = SUPPORT_DIR / "token"
LOG_PATH = SUPPORT_DIR / "tabsidebar.log"


def load_or_create_token(path: Path) -> str:
    """The websocket secret, kept across restarts so an open Toolbelt page stays connected."""
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)  # touch keeps the mode of a file that already existed
    path.write_text(token)
    return token


async def async_main(connection: iterm2.Connection) -> None:
    app = await iterm2.async_get_app(connection)
    token = load_or_create_token(TOKEN_PATH)
    sidebar = Sidebar(connection, app, FolderStore(STATE_PATH), page_version=page_version)

    # No access log: a page left open with an old link retries every second.
    runner = web.AppRunner(build_web_app(sidebar, ORIGIN, token), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, HOST, PORT).start()
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        log.error("port %s is in use; is tabsidebar already running (for example as the login agent)?", PORT)
        raise SystemExit(1) from error

    await register_toolbelt_tool(connection, f"{ORIGIN}/?token={token}")
    sidebar.mark_dirty()
    await asyncio.gather(
        sidebar.run_refresh_loop(),
        watch_iterm_layout(connection, sidebar),
        _raise_when_disconnected(connection),
    )


async def watch_iterm_layout(connection: iterm2.Connection, sidebar: Sidebar) -> None:
    async def forward(monitor) -> None:
        async with monitor as mon:
            while True:
                await mon.async_get()
                sidebar.mark_dirty()

    await asyncio.gather(
        forward(iterm2.LayoutChangeMonitor(connection)),
        forward(iterm2.NewSessionMonitor(connection)),
        forward(iterm2.SessionTerminationMonitor(connection)),
    )


async def _raise_when_disconnected(connection: iterm2.Connection) -> None:
    # Pending iTerm2 calls hang rather than fail when iTerm2 quits, so watch the socket itself.
    # The error ends async_main, and iterm2 then exits the process.
    await connection.websocket.wait_closed()
    raise ConnectionError("iTerm2 closed the API connection")


def _configure_logging() -> None:
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_PATH)],
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="tabsidebar", description="A folder sidebar for iTerm2's Toolbelt.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="run the sidebar in this terminal (the default)")
    commands.add_parser("install-agent", help="start the sidebar at login and whenever iTerm2 relaunches")
    commands.add_parser("uninstall-agent", help="remove the login agent")
    command = parser.parse_args().command

    if command == "install-agent":
        agent.install(SUPPORT_DIR)
    elif command == "uninstall-agent":
        agent.uninstall()
    else:
        _configure_logging()
        iterm2.run_forever(async_main, retry=True)


if __name__ == "__main__":
    main()
