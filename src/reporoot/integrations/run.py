"""Utilities for running external tools with visual annotation."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

_BOLD = "\033[1m"
_DIM = "\033[2m"
_YELLOW = "\033[33m"
_RESET = "\033[0m"


def _use_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def run_tool(cmd: list[str], *, cwd: Path) -> int:
    """Run an external tool, prefixing its output to distinguish it from reporoot's.

    Prints the command with a $ prefix (bold in color terminals),
    then streams the tool's stdout/stderr with a │ gutter.
    stdout lines go to sys.stdout (dim │), stderr lines go to
    sys.stderr (yellow │ in color terminals).

    Returns the process exit code.
    """
    color = _use_color()
    cmd_str = " ".join(cmd)

    if color:
        print(f"  {_BOLD}$ {cmd_str}{_RESET}")
    else:
        print(f"  $ {cmd_str}")

    out_prefix = f"  {_DIM}│{_RESET} " if color else "  │ "
    err_prefix = f"  {_YELLOW}│{_RESET} " if color else "  │ "

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def _stream(pipe: object, prefix: str, dest: object) -> None:
        assert pipe is not None
        for line in pipe:  # type: ignore[union-attr]
            print(f"{prefix}{line}", end="", file=dest)  # type: ignore[call-overload]

    t_err = threading.Thread(
        target=_stream, args=(proc.stderr, err_prefix, sys.stderr),
    )
    t_err.start()

    # Read stdout on the main thread
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"{out_prefix}{line}", end="")

    t_err.join()
    proc.wait()
    return proc.returncode
