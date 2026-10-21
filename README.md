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

1. Install the `tabsidebar` command:
   ```sh
   uv tool install git+https://github.com/<your-github-user>/tabsidebar
   ```
2. In iTerm2, turn on **Settings → General → Magic → Enable Python API**.
3. Start it at login, so it is always there when iTerm2 is:
   ```sh
   tabsidebar install-agent
   ```
   Or run `tabsidebar` in a terminal to try it first; it stops when you close that terminal or quit iTerm2.
   The first time, macOS or iTerm2 may ask you to allow it to control iTerm2. Allow it.
4. In iTerm2, open **View → Toolbelt → Show Toolbelt**, then check **Tab Folders** in the same submenu.

## Using it

- **+ Folder** adds a folder. Double-click a name or use **✎** to rename it, and **×** to delete it.
  Deleting a folder never closes tabs; they go back to Unsorted.
- Drag a tab onto a folder to file it, or onto a tab in a folder to place it before that tab.
  Unsorted always follows iTerm2's tab order.
- Click the dot next to a folder's name to give it a colour.
- **⚙** at the bottom right opens settings:
  - **Folder colours** switches between the **Default** palette and a **Custom** one. With Custom selected, click a
    colour to change it with the picker or a `#rrggbb` value; **Reset to default** starts over. A folder remembers
    its position in the palette, so switching palettes or editing a colour re-tints every folder that uses it.
  - **Colour iTerm tabs by folder** gives each tab in a coloured folder that colour in iTerm2's tab bar.
    Turning it off, or moving the tab out of the folder, restores the tab's own colour.

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

## Development

```sh
git clone https://github.com/<your-github-user>/tabsidebar && cd tabsidebar
uv run tabsidebar   # run from the checkout
uv run pytest       # tests
```

- `daemon.py` connects to iTerm2, serves the page, registers it in the Toolbelt, and exits when the iTerm2
  connection ends. It also holds the command line.
- `sidebar.py` keeps the tree in sync with iTerm2 and handles page commands. It is the only writer of tab colours
  and page updates, one publish at a time.
- `server.py` serves the page (`static/index.html`) and its websocket. `toolbelt.py` registers the page with
  iTerm2. `agent.py` installs the login agent.
- `model.py` (folders, palettes and settings), `titles.py` (Claude Code status) and `tabcolors.py` hold the logic,
  and are tested without iTerm2.

## License

MIT. See [LICENSE](LICENSE).
