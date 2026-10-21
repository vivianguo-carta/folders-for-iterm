"""The sidebar page shown in iTerm2's Toolbelt, and its websocket."""

from __future__ import annotations

import hmac
import json
import logging
from pathlib import Path

from aiohttp import WSMsgType, web

from tabsidebar.sidebar import BadCommand, Sidebar

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def build_web_app(sidebar: Sidebar, origin: str, token: str) -> web.Application:
    """`origin` stops browser pages; `token`, known only to pages this process opened, stops local processes."""

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def websocket(request: web.Request) -> web.WebSocketResponse:
        if request.headers.get("Origin") != origin or not hmac.compare_digest(
            request.query.get("token", ""), token
        ):
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await sidebar.add_client(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await _handle_message(sidebar, ws, msg.data)
        finally:
            sidebar.remove_client(ws)
        return ws

    web_app = web.Application()
    web_app.router.add_get("/", index)
    web_app.router.add_get("/ws", websocket)
    return web_app


async def _handle_message(sidebar: Sidebar, ws: web.WebSocketResponse, data: str) -> None:
    try:
        await sidebar.handle_command(json.loads(data))
    except (BadCommand, ValueError) as error:
        # A stale page can reference a folder another page deleted.
        log.info("ignored page command: %s", error)
    except Exception:
        log.exception("page command failed")
    else:
        return
    await sidebar.resync(ws)
