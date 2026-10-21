"""Folder state for the sidebar, independent of iTerm2.

Tabs are keyed by a UUID, not the iTerm2 tab id: iTerm2 reuses tab ids after a restart.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, NamedTuple

log = logging.getLogger(__name__)

UNSORTED_ID = "unsorted"
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
DEFAULT_PALETTE = (
    "#e5534b", "#e0823d", "#d4a72c", "#46a758", "#2bb3a3", "#3b82f6", "#8b5cf6", "#e05297", "#8b8d98",
)
PALETTE_DEFAULT, PALETTE_CUSTOM = "default", "custom"
PALETTE_NAMES = (PALETTE_DEFAULT, PALETTE_CUSTOM)


@dataclass(frozen=True)
class LiveTab:
    key: str
    tab_id: str
    title: str
    status: str | None = None


@dataclass
class Folder:
    id: str
    name: str
    tab_keys: list[str] = field(default_factory=list)
    # A slot in the active palette rather than a hex value, so switching palettes re-tints the folder.
    color_slot: int | None = None

    @classmethod
    def from_json(cls, raw: dict) -> Folder:
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            tab_keys=[k for k in raw.get("tab_keys", []) if isinstance(k, str)],
            color_slot=_slot_from_json(raw),
        )


class Group(NamedTuple):
    """One folder's open tabs, or the Unsorted pseudo-folder."""

    id: str
    name: str
    color_slot: int | None
    color: str | None
    tabs: list[LiveTab]


class FolderStore:
    """Folders, tab membership and sidebar settings, saved atomically to one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.folders: list[Folder] = []
        self.color_tabs = False
        self.palette_name = PALETTE_DEFAULT
        self.custom_palette = list(DEFAULT_PALETTE)
        self._seen_keys: set[str] = set()
        if path.exists():
            self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
            folders = [Folder.from_json(f) for f in raw["folders"]]
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            # Keep the unreadable file for inspection rather than failing on every start.
            aside = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            self.path.replace(aside)
            log.warning("could not read %s (%r); moved it to %s and started empty", self.path, error, aside)
            return
        self.folders = folders
        self.color_tabs = raw.get("color_tabs") is True
        if raw.get("palette") in PALETTE_NAMES:
            self.palette_name = raw["palette"]
        custom = raw.get("custom_palette")
        if isinstance(custom, list) and len(custom) == len(DEFAULT_PALETTE):
            self.custom_palette = [
                c if isinstance(c, str) and HEX_COLOR.fullmatch(c) else d for c, d in zip(custom, DEFAULT_PALETTE)
            ]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "folders": [vars(f) for f in self.folders],
            "color_tabs": self.color_tabs,
            "palette": self.palette_name,
            "custom_palette": self.custom_palette,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def create_folder(self, name: str) -> Folder:
        folder = Folder(id=uuid.uuid4().hex, name=name)
        self.folders.append(folder)
        self.save()
        return folder

    def rename_folder(self, folder_id: str, name: str) -> None:
        self._folder(folder_id).name = name
        self.save()

    @property
    def active_palette(self) -> tuple[str, ...]:
        return tuple(self.custom_palette) if self.palette_name == PALETTE_CUSTOM else DEFAULT_PALETTE

    def set_folder_color(self, folder_id: str, slot: int | None) -> None:
        """Gives a folder a palette slot's color, or clears it with None."""
        if slot is not None and not _is_slot(slot):
            raise ValueError(f"not a palette slot: {slot!r}")
        self._folder(folder_id).color_slot = slot
        self.save()

    def set_palette(self, name: str) -> None:
        if name not in PALETTE_NAMES:
            raise ValueError(f"unknown palette {name!r}")
        self.palette_name = name
        self.save()

    def set_custom_color(self, slot: int, color: str) -> None:
        if not _is_slot(slot):
            raise ValueError(f"not a palette slot: {slot!r}")
        if not (isinstance(color, str) and HEX_COLOR.fullmatch(color)):
            raise ValueError(f"not a #rrggbb color: {color!r}")
        self.custom_palette[slot] = color.lower()
        self.save()

    def reset_custom_palette(self) -> None:
        self.custom_palette = list(DEFAULT_PALETTE)
        self.save()

    def set_color_tabs(self, enabled: bool) -> None:
        self.color_tabs = enabled
        self.save()

    def delete_folder(self, folder_id: str) -> None:
        """Removes the folder; its tabs fall back to Unsorted."""
        self.folders.remove(self._folder(folder_id))
        self.save()

    def move_tab(self, key: str, folder_id: str, before_key: str | None = None) -> None:
        """Files a tab into a folder, before `before_key` or at the end; Unsorted ignores `before_key`."""
        if not isinstance(key, str):
            raise ValueError(f"tab key must be a string, not {key!r}")
        if key == before_key:
            return
        target = None if folder_id == UNSORTED_ID else self._folder(folder_id)
        self._detach(key)
        if target is not None:
            keys = target.tab_keys
            keys.insert(keys.index(before_key) if before_key in keys else len(keys), key)
        self.save()

    def sync_live_tabs(self, live: list[LiveTab]) -> None:
        """Forgets tabs that were open earlier in this run and have since closed.

        Keys never seen this run are kept: they may belong to tabs iTerm2 has
        not restored yet.
        """
        live_keys = {t.key for t in live}
        closed = self._seen_keys - live_keys
        self._seen_keys = live_keys
        detached = [k for k in closed if self._detach(k)]
        if detached:
            self.save()

    def groups(self, live: list[LiveTab]) -> Iterator[Group]:
        """Folders in order, each with its open tabs, then Unsorted with everything else in iTerm2 order."""
        by_key = {t.key: t for t in live}
        filed: set[str] = set()
        for folder in self.folders:
            tabs = [by_key[k] for k in folder.tab_keys if k in by_key]
            filed.update(t.key for t in tabs)
            yield Group(folder.id, folder.name, folder.color_slot, self._color_of(folder), tabs)
        yield Group(UNSORTED_ID, "Unsorted", None, None, [t for t in live if t.key not in filed])

    def tree(self, live: list[LiveTab]) -> list[dict]:
        """The folder tree as the sidebar page receives it."""
        return [_group_json(g) for g in self.groups(live)]

    def tab_colors(self, live: list[LiveTab]) -> dict[str, str | None]:
        """The iTerm2 tab color each open tab should have, by tab id; None means its own color."""
        colors: dict[str, str | None] = {t.tab_id: None for t in live}
        if self.color_tabs:
            for group in self.groups(live):
                for tab in group.tabs:
                    colors[tab.tab_id] = group.color
        return colors

    def _color_of(self, folder: Folder) -> str | None:
        return None if folder.color_slot is None else self.active_palette[folder.color_slot]

    def _folder(self, folder_id: str) -> Folder:
        for folder in self.folders:
            if folder.id == folder_id:
                return folder
        raise KeyError(folder_id)

    def _detach(self, key: str) -> bool:
        for folder in self.folders:
            if key in folder.tab_keys:
                folder.tab_keys.remove(key)
                return True
        return False


def _group_json(group: Group) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "color_slot": group.color_slot,
        "color": group.color,
        "editable": group.id != UNSORTED_ID,
        "tabs": [vars(t) for t in group.tabs],
    }


def _is_slot(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(DEFAULT_PALETTE)


def _slot_from_json(raw: dict) -> int | None:
    slot = raw.get("color_slot")
    if _is_slot(slot):
        return slot
    # Files written before palettes stored the default palette's hex value instead of a slot.
    color = raw.get("color")
    if isinstance(color, str) and color.lower() in DEFAULT_PALETTE:
        return DEFAULT_PALETTE.index(color.lower())
    return None
