from __future__ import annotations

import asyncio
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class WadResult:
    """Result of running a WAD command."""

    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined(self) -> str:
        if not self.stderr:
            return self.stdout
        if not self.stdout:
            return self.stderr
        return f"{self.stdout}\n{self.stderr}"


def _default_repo_path() -> Path:
    """Best-effort default repo path.

    WAD typically runs inside a git repository, but this MCP server is intended
    to be launched from whatever project repo the agent wants to control.

    We allow overriding via env var to support running the server from a
    different working directory.
    """

    env = os.environ.get("WAD_PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def _default_wad_bin() -> str:
    """Best-effort discovery of the `wad` executable.

    Priority:
    1) $WAD_BIN if set
    2) `wad` in PATH
    """

    if os.environ.get("WAD_BIN"):
        return os.environ["WAD_BIN"]

    return "wad"


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-(max_chars // 2) :]
    return (
        head
        + "\n\n...<output truncated>...\n\n"
        + tail
    )


async def run_wad(
    *args: str,
    repo_path: str | None = None,
    wad_bin: str | None = None,
    extra_env: dict[str, str] | None = None,
    timeout_s: float | None = None,
    max_output_chars: int = 20000,
) -> WadResult:
    """Run a WAD command asynchronously.

    Args:
        args: Arguments passed to `wad`.
        repo_path: Directory to run in. Defaults to $WAD_PROJECT_ROOT or cwd.
        wad_bin: Path/name of `wad`. Defaults to $WAD_BIN, ./wad, or wad in PATH.
        extra_env: Extra environment variables.
        timeout_s: Optional timeout.
        max_output_chars: Combined stdout/stderr truncation limit.

    Returns:
        WadResult with stdout/stderr captured.
    """

    cwd_path = Path(repo_path).expanduser().resolve() if repo_path else _default_repo_path()
    exe = wad_bin or _default_wad_bin()

    cmd = [exe, *args]

    env = os.environ.copy()
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    # Prefer disabling ANSI output when supported.
    # WAD uses hardcoded color codes today, but this helps future changes.
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        stdout_b, stderr_b = await proc.communicate()
        return WadResult(
            command=cmd,
            cwd=str(cwd_path),
            returncode=124,
            stdout=_truncate(stdout_b.decode(errors="replace"), max_chars=max_output_chars),
            stderr=_truncate(
                (stderr_b.decode(errors="replace") + "\nTimed out"),
                max_chars=max_output_chars,
            ),
        )

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")

    # Apply truncation after decode; keep each stream within max_output_chars.
    stdout = _truncate(stdout, max_chars=max_output_chars)
    stderr = _truncate(stderr, max_chars=max_output_chars)

    return WadResult(
        command=cmd,
        cwd=str(cwd_path),
        returncode=proc.returncode or 0,
        stdout=stdout,
        stderr=stderr,
    )


def format_command(cmd: Iterable[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)
