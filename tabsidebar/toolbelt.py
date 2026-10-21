"""Registers the sidebar page as a tool in iTerm2's Toolbelt."""

from __future__ import annotations

import iterm2

TOOL_NAME = "Tab Folders"
TOOL_IDENTIFIER = "local.tabsidebar.toolbelt"


async def register_toolbelt_tool(connection: iterm2.Connection, url: str) -> None:
    await iterm2.tool.async_register_web_view_tool(connection, TOOL_NAME, TOOL_IDENTIFIER, False, url)
