import asyncio
import json

from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer

from fakes import FakeApp, FakeColorizer, FakeTab, SidebarWithoutWatchers
from tabsidebar.model import FolderStore
from tabsidebar.server import build_web_app, page_version

TOKEN = "per-run-secret"


def run_against_server(tmp_path, scenario):
    sidebar = SidebarWithoutWatchers(
        connection=None,
        app=FakeApp(FakeTab("1", "-zsh")),
        store=FolderStore(tmp_path / "state.json"),
        colorizer=FakeColorizer(),
        page_version=lambda: "v-test",
    )

    async def main():
        server = TestServer(build_web_app(sidebar, origin="http://127.0.0.1:47821", token=TOKEN))
        async with TestClient(server) as client:
            return await scenario(client)

    return asyncio.run(main())


async def handshake_status(client, origin, token):
    try:
        ws = await client.ws_connect(f"/ws?token={token}", headers={"Origin": origin})
    except WSServerHandshakeError as error:
        return error.status
    await ws.close()
    return 101


def test_websocket_refuses_other_origins_and_missing_or_wrong_tokens(tmp_path):
    async def scenario(client):
        return [
            await handshake_status(client, "https://evil.example", TOKEN),
            await handshake_status(client, "http://127.0.0.1:47821", ""),
            await handshake_status(client, "http://127.0.0.1:47821", "guessed"),
            await handshake_status(client, "http://127.0.0.1:47821", TOKEN),
        ]

    assert run_against_server(tmp_path, scenario) == [403, 403, 403, 101]


def test_a_stale_command_resyncs_the_page_and_keeps_the_socket_open(tmp_path):
    async def scenario(client):
        ws = await client.ws_connect(f"/ws?token={TOKEN}", headers={"Origin": "http://127.0.0.1:47821"})
        first = json.loads((await ws.receive()).data)
        await ws.send_str(json.dumps({"action": "delete_folder", "folder_id": "deleted-by-another-page"}))
        resync = json.loads((await ws.receive()).data)
        await ws.send_str(json.dumps({"action": "create_folder", "name": "api"}))
        after = json.loads((await ws.receive()).data)
        await ws.close()
        return first["type"], resync["type"], [f["name"] for f in after["folders"]]

    assert run_against_server(tmp_path, scenario) == ("tree", "tree", ["api", "Unsorted"])


def test_non_json_message_is_ignored_and_the_page_resynced(tmp_path):
    async def scenario(client):
        ws = await client.ws_connect(f"/ws?token={TOKEN}", headers={"Origin": "http://127.0.0.1:47821"})
        await ws.receive()
        await ws.send_str("not json")
        reply = json.loads((await ws.receive()).data)
        await ws.close()
        return reply["type"]

    assert run_against_server(tmp_path, scenario) == "tree"


def test_the_page_is_served_uncached_and_stamped_with_its_current_version(tmp_path):
    async def scenario(client):
        response = await client.get("/")
        return response.headers.get("Cache-Control"), await response.text()

    cache_control, html = run_against_server(tmp_path, scenario)

    assert cache_control == "no-store"
    assert f'const PAGE_VERSION = "{page_version()}";' in html


def test_every_update_tells_pages_the_current_page_version(tmp_path):
    async def scenario(client):
        ws = await client.ws_connect(f"/ws?token={TOKEN}", headers={"Origin": "http://127.0.0.1:47821"})
        first = json.loads((await ws.receive()).data)
        await ws.close()
        return first["page_version"]

    assert run_against_server(tmp_path, scenario) == "v-test"
