import subprocess
import sys

from kai_devtools import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "kai_devtools", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
