import plistlib
import subprocess
import sys
from pathlib import Path

from tabsidebar.agent import LABEL, agent_plist


def test_agent_starts_at_login_and_restarts_the_sidebar_whenever_it_exits(tmp_path):
    plist = agent_plist("/opt/tools/tabsidebar/bin/python", tmp_path)

    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == ["/opt/tools/tabsidebar/bin/python", "-m", "tabsidebar"]
    assert (plist["RunAtLoad"], plist["KeepAlive"]) == (True, True)
    assert Path(plist["StandardErrorPath"]).parent == tmp_path


def test_agent_definition_is_a_valid_launchd_plist(tmp_path):
    path = tmp_path / f"{LABEL}.plist"
    path.write_bytes(plistlib.dumps(agent_plist(sys.executable, tmp_path)))

    lint = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)

    assert lint.returncode == 0, lint.stdout


def test_the_agents_command_line_reaches_the_sidebar_entry_point():
    # The agent runs `python -m tabsidebar`; --help proves that resolves to the CLI without starting anything.
    result = subprocess.run([sys.executable, "-m", "tabsidebar", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "install-agent" in result.stdout
