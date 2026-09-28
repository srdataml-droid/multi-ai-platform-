"""deploy/aws/setup-agent.sh installs examples/hermes_agent.py only if the download matches
the hash written in the script, so a changed agent must come with a changed hash."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy" / "aws" / "setup-agent.sh"


def test_the_setup_script_pins_the_agent_as_it_is_now() -> None:
    m = re.search(r"^AGENT_SHA256=([0-9a-f]{64})$", SCRIPT.read_text(), re.MULTILINE)
    assert m, "AGENT_SHA256 line missing"
    now = hashlib.sha256((ROOT / "examples" / "hermes_agent.py").read_bytes()).hexdigest()
    assert m.group(1) == now, f"examples/hermes_agent.py changed: set AGENT_SHA256={now}"


def test_the_setup_script_is_valid_bash() -> None:
    bash = shutil.which("bash")
    assert bash is not None
    subprocess.run([bash, "-n", str(SCRIPT)], check=True)
