# tabsidebar

Group your iTerm2 tabs into folders, in a sidebar that lives in iTerm2's Toolbelt.

- Make your own folders and drag tabs into them; everything else sits in **Unsorted**.
- Click a tab to switch to it. Titles stay in sync with iTerm2, including tabs you rename.
- Claude Code tabs get a status dot: pulsing orange while Claude is working, green while it is waiting for you.
- Give folders colours, and optionally colour each iTerm2 tab to match its folder.

## Requirements

- macOS with [iTerm2](https://iterm2.com) (tested with iTerm2 3.6).
- [uv](https://docs.astral.sh/uv/) to install it: `brew install uv`.

## Install

You only do this once. After that the sidebar starts by itself at login and whenever iTerm2 relaunches, with no
terminal left running.

1. Install the `tabsidebar` command:
   ```sh
   uv tool install git+https://github.com/vivianguo-carta/folders-for-iterm
   ```
2. In iTerm2, turn on **Settings → General → Magic → Enable Python API**.
3. Install the login agent, which starts the sidebar now and keeps it running:
   ```sh
   tabsidebar install-agent
   ```
   The first time, macOS or iTerm2 may ask you to allow it to control iTerm2. Allow it.
4. In iTerm2, open **View → Toolbelt → Show Toolbelt**, then check **Tab Folders** in the same submenu.

To try it without the agent, run `tabsidebar` in a terminal instead of step 3. It stops when you close that
terminal or quit iTerm2. Stop it before installing the agent, or the agent finds port 47821 in use.

## Update

The agent runs the installed copy, so reinstall it and restart the agent:

```sh
uv tool install --reinstall git+https://github.com/vivianguo-carta/folders-for-iterm
tabsidebar install-agent
```

## Using it

- **+ Folder** adds a folder. Double-click a name or use **✎** to rename it, and **×** to delete it.
  Deleting a folder never closes tabs; they go back to Unsorted.
- Double-click a tab to rename it in iTerm2 (Enter saves, Esc cancels). Clearing the name gives the tab back its
  own title from iTerm2.
- Drag a tab onto a folder to file it, or onto a tab in a folder to place it before that tab.
  Unsorted always follows iTerm2's tab order.
- Click the dot next to a folder's name to give it a colour.
- **⚙** at the bottom right opens settings:
  - **Folder colours** switches between the **Default** palette and a **Custom** one, and shows the selected
    palette's colours. With Custom selected, click a colour to change it with the picker or a `#rrggbb` value;
    **Reset to default** starts over. A folder remembers
    its position in the palette, so switching palettes or editing a colour re-tints every folder that uses it.
  - **Colour iTerm tabs by folder** gives each tab in a coloured folder that colour in iTerm2's tab bar.
    Turning it off, or moving the tab out of the folder, restores the tab's own colour.
  - **Order iTerm tabs like the sidebar** keeps each window's tabs in the sidebar's order: folders first, then
    Unsorted. Dragging a tab in the sidebar moves it in iTerm2 too. Tabs never move to another window, and a filed
    tab dragged elsewhere in iTerm2's tab bar moves back.

## Troubleshooting

- **Tab Folders is missing from the Toolbelt menu.** The sidebar is not running. Run `tabsidebar`, or
  `tabsidebar install-agent` to keep it running.
- **The sidebar is gone after closing it with ×.** If it was the only Toolbelt tool, iTerm2 hides the whole
  Toolbelt. Check **Tab Folders** again and also choose **View → Toolbelt → Show Toolbelt**.
- **The sidebar says "disconnected — retrying…".** The sidebar stopped, for example because iTerm2 restarted
  and the login agent is not installed. Start it again.
- **"port 47821 is in use".** Another copy is already running, often the login agent. Use that one, or set
  `TABSIDEBAR_PORT` to run a second copy.
- Logs are in `~/Library/Application Support/tabsidebar/`: `tabsidebar.log`, plus `agent.err.log` for the
  login agent.

## Uninstall

```sh
tabsidebar uninstall-agent
uv tool uninstall tabsidebar
rm -rf ~/Library/Application\ Support/tabsidebar
```

## What it stores and changes

- Your folders and settings: `~/Library/Application Support/tabsidebar/state.json`. If the file cannot be read,
  it is moved aside as `state.json.corrupt-<time>` and the sidebar starts empty.
- A secret in `~/Library/Application Support/tabsidebar/token`, readable only by your user. The sidebar's local
  web server (`http://127.0.0.1:47821`) only accepts the Toolbelt page, which it checks by origin and this secret.
- Two iTerm2 variables:
  - `user.tabsidebar_key` on each tab, so a tab keeps its folder even though iTerm2 reuses tab ids. Whether a tab
    keeps its folder across an iTerm2 restart depends on iTerm2 restoring tab variables; this is not verified.
  - `user.tabsidebar_original_tab_color` on each session it colours, so the tab's own colour can be restored, even
    after the sidebar restarts.
- With **Colour iTerm tabs by folder** on, it changes tab colours for those sessions only; your iTerm2 profiles
  are not modified.
- With **Order iTerm tabs like the sidebar** on, it reorders tabs within their windows.

## Development

```sh
git clone https://github.com/vivianguo-carta/folders-for-iterm && cd folders-for-iterm
uv run tabsidebar   # run from the checkout
uv run pytest       # tests
```

- `daemon.py` connects to iTerm2, serves the page, registers it in the Toolbelt, and exits when the iTerm2
  connection ends. It also holds the command line.
- `sidebar.py` keeps the tree in sync with iTerm2 and handles page commands. It is the only writer of tab colours,
  tab order and page updates, one publish at a time.
- `server.py` serves the page (`static/index.html`) and its websocket. `toolbelt.py` registers the page with
  iTerm2. `agent.py` installs the login agent.
- `model.py` (folders, palettes and settings), `titles.py` (Claude Code status) and `tabcolors.py` hold the logic,
  and are tested without iTerm2.

## License

MIT. See [LICENSE](LICENSE).
