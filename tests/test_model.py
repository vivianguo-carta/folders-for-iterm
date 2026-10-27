import json

import pytest

from tabsidebar.model import DEFAULT_PALETTE, UNSORTED_ID, FolderStore, LiveTab


def tab(key: str, title: str = "") -> LiveTab:
    return LiveTab(key=key, tab_id=f"id-{key}", title=title or key)


def tree_shape(store: FolderStore, live: list[LiveTab]) -> dict[str, list[str]]:
    return {f["name"]: [t["key"] for t in f["tabs"]] for f in store.tree(live)}


def test_unfiled_tabs_appear_in_unsorted_in_iterm_order(tmp_path):
    store = FolderStore(tmp_path / "state.json")

    assert tree_shape(store, [tab("b"), tab("a")]) == {"Unsorted": ["b", "a"]}


def test_filed_tab_shows_under_its_folder_with_live_title(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.move_tab("a", api.id)

    folders = store.tree([tab("a", title="vim models.py"), tab("b")])

    assert folders[0]["tabs"] == [{"key": "a", "tab_id": "id-a", "title": "vim models.py", "status": None}]
    assert [t["key"] for t in folders[1]["tabs"]] == ["b"]


def test_dropping_on_a_tab_inserts_before_it_including_moving_down(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    for key in "abc":
        store.move_tab(key, api.id)

    store.move_tab("a", api.id, before_key="c")

    assert tree_shape(store, [tab("a"), tab("b"), tab("c")])["api"] == ["b", "a", "c"]


def test_moving_tab_to_unsorted_removes_it_from_folder(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.move_tab("a", api.id)

    store.move_tab("a", UNSORTED_ID)

    assert tree_shape(store, [tab("a")]) == {"api": [], "Unsorted": ["a"]}


def test_deleting_folder_returns_its_tabs_to_unsorted(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.move_tab("a", api.id)

    store.delete_folder(api.id)

    assert tree_shape(store, [tab("a")]) == {"Unsorted": ["a"]}


# Each persistence test ends on the mutator it names, so a missing save in that mutator fails the test.


def test_created_folder_survives_reload(tmp_path):
    path = tmp_path / "state.json"

    FolderStore(path).create_folder("api")

    assert [f.name for f in FolderStore(path).folders] == ["api"]


def test_folder_rename_survives_reload(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    api = store.create_folder("api")

    store.rename_folder(api.id, "backend")

    assert FolderStore(path).folders[0].name == "backend"


def test_tab_membership_survives_reload(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    api = store.create_folder("api")

    store.move_tab("a", api.id)

    assert tree_shape(FolderStore(path), [tab("a")]) == {"api": ["a"], "Unsorted": []}


def test_folder_color_survives_reload(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    api = store.create_folder("api")

    store.set_folder_color(api.id, 5)

    assert FolderStore(path).folders[0].color_slot == 5


def test_coloring_toggle_survives_reload(tmp_path):
    path = tmp_path / "state.json"

    FolderStore(path).set_color_tabs(True)

    assert FolderStore(path).color_tabs is True


def test_ordering_toggle_survives_reload(tmp_path):
    path = tmp_path / "state.json"

    FolderStore(path).set_order_tabs(True)

    assert FolderStore(path).order_tabs is True


def test_tab_order_lists_folders_in_order_then_unsorted_in_iterm_order(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api, web = store.create_folder("api"), store.create_folder("web")
    store.move_tab("c", web.id)
    store.move_tab("d", api.id)
    store.move_tab("b", api.id, before_key="d")

    order = store.tab_order([tab("a"), tab("b"), tab("c"), tab("d"), tab("e")])

    assert order == ["id-b", "id-d", "id-c", "id-a", "id-e"]


def test_tabs_take_their_folder_color_only_when_coloring_is_enabled(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.set_folder_color(api.id, 5)  # blue in the default palette
    store.move_tab("a", api.id)
    live = [tab("a"), tab("b")]

    off = store.tab_colors(live)
    store.set_color_tabs(True)
    on = store.tab_colors(live)

    assert off == {"id-a": None, "id-b": None}
    assert on == {"id-a": "#3b82f6", "id-b": None}


def test_invalid_custom_color_is_rejected(tmp_path):
    store = FolderStore(tmp_path / "state.json")

    with pytest.raises(ValueError):
        store.set_custom_color(0, "blue; background: url(x)")


def test_closed_tab_is_forgotten_but_never_seen_tab_is_kept(tmp_path):
    # A tab not yet seen this run may still be restored by iTerm2, so only tabs that closed mid-run are dropped.
    path = tmp_path / "state.json"
    store = FolderStore(path)
    api = store.create_folder("api")
    store.move_tab("closed", api.id)
    store.move_tab("not-restored-yet", api.id)
    store.sync_live_tabs([tab("closed")])

    store.sync_live_tabs([])

    assert FolderStore(path).folders[0].tab_keys == ["not-restored-yet"]


def test_closing_several_filed_tabs_at_once_forgets_all_of_them(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    api = store.create_folder("api")
    store.move_tab("a", api.id)
    store.move_tab("b", api.id)
    store.sync_live_tabs([tab("a"), tab("b")])

    store.sync_live_tabs([])

    assert FolderStore(path).folders[0].tab_keys == []


def test_moving_to_an_unknown_folder_leaves_the_tab_where_it_was(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.move_tab("a", api.id)

    with pytest.raises(KeyError):
        store.move_tab("a", "deleted-elsewhere")

    assert tree_shape(store, [tab("a")])["api"] == ["a"]


def test_moving_between_folders_before_a_key_not_in_the_target_appends(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api, web = store.create_folder("api"), store.create_folder("web")
    store.move_tab("a", api.id)
    store.move_tab("b", web.id)

    store.move_tab("a", web.id, before_key="not-in-web")

    assert tree_shape(store, [tab("a"), tab("b")]) == {"api": [], "web": ["b", "a"], "Unsorted": []}


def test_non_string_tab_key_is_rejected(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")

    with pytest.raises(ValueError):
        store.move_tab(["not", "a", "key"], api.id)


def test_only_real_folders_are_editable_in_the_tree(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    store.create_folder("api")

    assert [(f["name"], f["editable"]) for f in store.tree([])] == [("api", True), ("Unsorted", False)]


def test_unreadable_state_file_is_set_aside_and_the_store_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ not json")

    store = FolderStore(path)

    assert store.folders == []
    assert not path.exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("state.json.corrupt-")]


def test_loaded_values_that_fail_validation_fall_back_to_defaults(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "folders": [{"id": "f1", "name": "api", "tab_keys": ["a", 7], "color_slot": 99, "extra": 1}],
        "palette": "neon",
        "custom_palette": ["#000000", "red"],
        "color_tabs": "yes",
        "order_tabs": 1,
    }))

    store = FolderStore(path)

    assert (store.folders[0].tab_keys, store.folders[0].color_slot) == (["a"], None)
    assert (store.palette_name, store.custom_palette) == ("default", list(DEFAULT_PALETTE))
    assert (store.color_tabs, store.order_tabs) == (False, False)


def test_switching_palettes_retints_folders_by_slot(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.set_folder_color(api.id, 5)
    store.set_custom_color(5, "#123456")

    default = store.tree([])[0]["color"]
    store.set_palette("custom")
    custom = store.tree([])[0]["color"]

    assert (default, custom) == (DEFAULT_PALETTE[5], "#123456")


def test_editing_a_custom_slot_recolors_tabs_of_folders_using_it(tmp_path):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")
    store.set_folder_color(api.id, 2)
    store.move_tab("a", api.id)
    store.set_color_tabs(True)
    store.set_palette("custom")

    store.set_custom_color(2, "#ABCDEF")

    assert store.tab_colors([tab("a")]) == {"id-a": "#abcdef"}


def test_custom_palette_and_choice_survive_reload(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    store.set_custom_color(0, "#101010")

    FolderStore(path).set_palette("custom")

    reloaded = FolderStore(path)
    assert (reloaded.palette_name, reloaded.custom_palette[0]) == ("custom", "#101010")


def test_reset_restores_the_default_colors_in_the_custom_palette(tmp_path):
    path = tmp_path / "state.json"
    store = FolderStore(path)
    store.set_custom_color(0, "#101010")

    store.reset_custom_palette()

    assert FolderStore(path).custom_palette == list(DEFAULT_PALETTE)


@pytest.mark.parametrize("slot", [-1, 9, "3", True, 2.0])
def test_folder_color_must_be_a_palette_slot(tmp_path, slot):
    store = FolderStore(tmp_path / "state.json")
    api = store.create_folder("api")

    with pytest.raises(ValueError):
        store.set_folder_color(api.id, slot)


def test_folders_saved_with_hex_colors_load_as_their_default_palette_slot(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"folders": [
        {"id": "f1", "name": "red", "tab_keys": [], "color": "#E5534B"},
        {"id": "f2", "name": "off-palette", "tab_keys": [], "color": "#000001"},
    ]}))

    store = FolderStore(path)

    assert [f.color_slot for f in store.folders] == [0, None]
