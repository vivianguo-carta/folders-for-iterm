"""Installs a launchd agent that keeps the sidebar running whenever you are logged in."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "local.tabsidebar"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def agent_plist(python: str, log_dir: Path) -> dict:
    """The agent definition: start at login, and start again whenever the sidebar exits.

    The sidebar exits when iTerm2 quits and, on start, waits for iTerm2 without launching it.
    """
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "tabsidebar"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "agent.out.log"),
        "StandardErrorPath": str(log_dir / "agent.err.log"),
    }


def install(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _bootout()  # replace an earlier install, e.g. one pointing at an older Python
    with PLIST_PATH.open("wb") as file:
        plistlib.dump(agent_plist(sys.executable, log_dir), file)
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST_PATH)], check=True)
    print(f"Installed {PLIST_PATH}; the sidebar now starts at login and after iTerm2 relaunches.")


def uninstall() -> None:
    _bootout()
    PLIST_PATH.unlink(missing_ok=True)
    print("Removed the tabsidebar login agent.")


def _bootout() -> None:
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)


def _domain() -> str:
    return f"gui/{os.getuid()}"
