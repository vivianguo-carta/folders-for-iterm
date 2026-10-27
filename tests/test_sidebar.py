import asyncio

import pytest

from fakes import FakeApp, FakeColorizer, FakeTab, FakeWindow, RecordingClient, SidebarWithoutWatchers
from tabsidebar.model import FolderStore
from tabsidebar.sidebar import BadCommand


def make_sidebar(tmp_path, *tabs):
    return SidebarWithoutWatchers(
        connection=None,
        app=FakeApp(*tabs),
        store=FolderStore(tmp_path / "state.json"),
        colorizer=FakeColorizer(),
    )


async def refresh_once(sidebar):
    sidebar.mark_dirty()
    loop = asyncio.create_task(sidebar.run_refresh_loop())
    await asyncio.sleep(0.05)
    loop.cancel()


def tab_titles(message):
    return [t["title"] for f in message["folders"] for t in f["tabs"]]


def test_refresh_loop_keeps_running_after_a_failed_refresh(tmp_path):
    flaky = FakeTab("1", "-zsh")
    flaky.fail_next_read = True
    sidebar = make_sidebar(tmp_path, flaky)

    async def scenario():
        loop = asyncio.create_task(sidebar.run_refresh_loop())
        sidebar.mark_dirty()
        await asyncio.sleep(0.05)
        sidebar.mark_dirty()
        await asyncio.sleep(0.05)
        loop.cancel()
        return [t.title for t in sidebar.live]

    assert asyncio.run(scenario()) == ["-zsh"]


def test_a_failing_client_is_dropped_without_starving_the_others(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "-zsh"))
    closing, healthy = RecordingClient(fail=True), RecordingClient()

    async def scenario():
        await sidebar.add_client(closing)
        await sidebar.add_client(healthy)
        await refresh_once(sidebar)
        await sidebar.handle_command({"action": "create_folder", "name": "api"})

    asyncio.run(scenario())

    assert closing not in sidebar._clients
    assert [m["folders"][0]["name"] for m in healthy.messages][-1] == "api"


def test_a_spinner_frame_does_not_resend_an_unchanged_tree(tmp_path):
    claude = FakeTab("1", "◐ Fix login (node)")
    sidebar = make_sidebar(tmp_path, claude)
    client = RecordingClient()

    async def scenario():
        await refresh_once(sidebar)
        await sidebar.add_client(client)
        sidebar._titles_by_tab_id["1"] = "◑ Fix login (node)"  # what the title watcher records
        await refresh_once(sidebar)

    asyncio.run(scenario())

    assert [tab_titles(m) for m in client.messages] == [["Fix login"]]


def test_moving_a_key_that_is_not_an_open_tab_is_rejected(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "-zsh"))

    async def scenario():
        await refresh_once(sidebar)
        folder = sidebar.store.create_folder("api")
        with pytest.raises(BadCommand):
            await sidebar.handle_command({"action": "move_tab", "key": "dragged text", "folder_id": folder.id})

    asyncio.run(scenario())

    assert sidebar.store.folders[0].tab_keys == []


@pytest.mark.parametrize("command", [[], "x", {"action": "rm -rf"}, {"action": "rename_folder"}])
def test_malformed_commands_are_rejected_as_bad_commands(tmp_path, command):
    sidebar = make_sidebar(tmp_path)

    with pytest.raises(BadCommand):
        asyncio.run(sidebar.handle_command(command))


def test_publishes_from_commands_and_refreshes_never_overlap(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "-zsh"))

    async def scenario():
        await asyncio.gather(
            refresh_once(sidebar),
            sidebar.handle_command({"action": "set_color_tabs", "enabled": True}),
            sidebar.handle_command({"action": "create_folder", "name": "api"}),
        )

    asyncio.run(scenario())

    assert sidebar.colorizer.max_in_flight == 1


def iterm_order(sidebar):
    return [[t.tab_id for t in w.tabs] for w in sidebar.app.terminal_windows]


def file_last_tab_into_a_new_folder(sidebar):
    async def scenario():
        await refresh_once(sidebar)
        await sidebar.handle_command({"action": "create_folder", "name": "api"})
        folder_id = sidebar.store.folders[0].id
        await sidebar.handle_command({"action": "move_tab", "key": sidebar.live[-1].key, "folder_id": folder_id})

    asyncio.run(scenario())


def test_filing_a_tab_moves_it_first_in_iterm_when_ordering_is_on(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "a"), FakeTab("2", "b"), FakeTab("3", "c"))
    sidebar.store.set_order_tabs(True)

    file_last_tab_into_a_new_folder(sidebar)

    assert iterm_order(sidebar) == [["3", "1", "2"]]


def test_iterm_tab_order_is_left_alone_when_ordering_is_off(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "a"), FakeTab("2", "b"), FakeTab("3", "c"))

    file_last_tab_into_a_new_folder(sidebar)

    assert iterm_order(sidebar) == [["1", "2", "3"]]
    assert sidebar.app.terminal_windows[0].reorders == 0


def test_ordering_keeps_tabs_in_their_own_window(tmp_path):
    sidebar = make_sidebar(tmp_path)
    sidebar.app.terminal_windows = [
        FakeWindow([FakeTab("1", "a"), FakeTab("2", "b")]),
        FakeWindow([FakeTab("3", "c"), FakeTab("4", "d")]),
    ]
    sidebar.store.set_order_tabs(True)

    file_last_tab_into_a_new_folder(sidebar)

    assert iterm_order(sidebar) == [["1", "2"], ["4", "3"]]


def test_a_window_already_in_order_is_not_reordered(tmp_path):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "a"), FakeTab("2", "b"))
    sidebar.store.set_order_tabs(True)

    asyncio.run(refresh_once(sidebar))

    assert sidebar.app.terminal_windows[0].reorders == 0


def test_activate_switches_to_the_clicked_tab(tmp_path):
    tab = FakeTab("1", "-zsh")
    sidebar = make_sidebar(tmp_path, tab)

    asyncio.run(sidebar.handle_command({"action": "activate", "tab_id": "1"}))

    assert tab.activated


def test_renaming_a_tab_sets_its_iterm_title(tmp_path):
    tab = FakeTab("1", "-zsh")
    sidebar = make_sidebar(tmp_path, tab)

    asyncio.run(sidebar.handle_command({"action": "rename_tab", "tab_id": "1", "title": "api server"}))

    assert tab.title_override == "api server"


def test_a_backslash_in_a_new_tab_title_is_kept_literally(tmp_path):
    # iTerm2 would otherwise read \(x) as an expression to interpolate.
    tab = FakeTab("1", "-zsh")
    sidebar = make_sidebar(tmp_path, tab)

    asyncio.run(sidebar.handle_command({"action": "rename_tab", "tab_id": "1", "title": "C:\\temp \\(x)"}))

    assert tab.title_override == "C:\\\\temp \\\\(x)"


@pytest.mark.parametrize("command", [
    {"action": "rename_tab", "tab_id": "closed", "title": "x"},
    {"action": "rename_tab", "tab_id": "1", "title": 42},
    {"action": "rename_tab", "tab_id": "1", "title": "x" * 201},
])
def test_bad_tab_renames_are_rejected(tmp_path, command):
    sidebar = make_sidebar(tmp_path, FakeTab("1", "-zsh"))

    with pytest.raises(BadCommand):
        asyncio.run(sidebar.handle_command(command))
