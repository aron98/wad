from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from fastmcp.server.context import Context
from fastmcp.server.dependencies import Progress

from wad_mcp_server.status import WadStatus, now_rfc3339, parse_wad_status_line


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
    return head + "\n\n...<output truncated>...\n\n" + tail


async def run_wad(
    *args: str,
    repo_path: str | None = None,
    wad_bin: str | None = None,
    extra_env: dict[str, str] | None = None,
    timeout_s: float | None = None,
    max_output_chars: int = 20000,
) -> WadResult:
    """Run a WAD command asynchronously.

    This helper captures stdout/stderr once the process finishes.

    For long-running commands where clients want incremental status, prefer
    :func:`run_wad_with_status`.

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


async def _apply_status_update(
    *,
    ctx: Context,
    progress: Progress,
    status: WadStatus,
) -> None:
    """Send a status update to the MCP client.

    In background-task mode, Progress.set_message() is persisted in Docket and is
    surfaced to clients as MCP task statusMessage (and optionally via
    notifications/tasks/status).

    In immediate mode, it still provides a structured log + best-effort progress
    notifications (if the request includes a progress token).
    """

    # Ensure every message has a timestamp for client-side ordering.
    if status.ts is None:
        status = WadStatus(
            code=status.code,
            state=status.state,
            message=status.message,
            step=status.step,
            total=status.total,
            ts=now_rfc3339(),
        )

    msg = status.to_status_message()

    with contextlib.suppress(Exception):
        await progress.set_message(msg)

    with contextlib.suppress(Exception):
        await ctx.log(
            status.message,
            level="info",
            logger_name="wad.status",
            extra=status.to_dict(),
        )

    # If the client provided a progressToken for the request, this will emit
    # MCP notifications/progress.
    if status.step is not None:
        with contextlib.suppress(Exception):
            await ctx.report_progress(status.step, status.total, status.message)


async def run_wad_with_status(
    *args: str,
    ctx: Context,
    progress: Progress,
    repo_path: str | None = None,
    wad_bin: str | None = None,
    extra_env: dict[str, str] | None = None,
    timeout_s: float | None = None,
    max_output_chars: int = 20000,
    on_status: Callable[[WadStatus], Awaitable[None]] | None = None,
) -> WadResult:
    """Run a WAD command while emitting incremental status/progress updates.

    The `wad` bash script emits machine-readable lines prefixed with:

        `WAD_STATUS { ...json... }`

    When these markers are observed, we:
    - persist the JSON into the MCP task `statusMessage` (via Docket Progress)
    - emit an MCP log message with `extra` containing the same JSON

    Args:
        args: Arguments passed to `wad`.
        ctx: FastMCP Context (injected).
        progress: FastMCP Progress dependency (injected).
        repo_path: Directory to run in. Defaults to $WAD_PROJECT_ROOT or cwd.
        wad_bin: Path/name of `wad`.
        extra_env: Extra environment variables.
        timeout_s: Optional timeout.
        max_output_chars: Combined stdout/stderr truncation limit.
        on_status: Optional callback invoked for each parsed status update.

    Returns:
        WadResult with stdout/stderr captured.
    """

    cwd_path = Path(repo_path).expanduser().resolve() if repo_path else _default_repo_path()
    exe = wad_bin or _default_wad_bin()

    cmd = [exe, *args]

    env = os.environ.copy()
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    # Enable structured status marker emission from the `wad` bash script.
    env.setdefault("WAD_MCP_STATUS", "1")

    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    async def _reader(stream: asyncio.StreamReader | None, sink: list[str]) -> None:
        if stream is None:
            return
        while True:
            line_b = await stream.readline()
            if not line_b:
                return
            line = line_b.decode(errors="replace")
            sink.append(line)

            status = parse_wad_status_line(line.strip())
            if status is None:
                continue

            await _apply_status_update(ctx=ctx, progress=progress, status=status)
            if on_status is not None:
                await on_status(status)

    reader_tasks = [
        asyncio.create_task(_reader(proc.stdout, stdout_buf)),
        asyncio.create_task(_reader(proc.stderr, stderr_buf)),
    ]

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return WadResult(
            command=cmd,
            cwd=str(cwd_path),
            returncode=124,
            stdout=_truncate("".join(stdout_buf), max_chars=max_output_chars),
            stderr=_truncate("".join(stderr_buf) + "\nTimed out", max_chars=max_output_chars),
        )
    finally:
        # Ensure reader tasks drain remaining output.
        with contextlib.suppress(Exception):
            await asyncio.gather(*reader_tasks)

    stdout = _truncate("".join(stdout_buf), max_chars=max_output_chars)
    stderr = _truncate("".join(stderr_buf), max_chars=max_output_chars)

    return WadResult(
        command=cmd,
        cwd=str(cwd_path),
        returncode=proc.returncode or 0,
        stdout=stdout,
        stderr=stderr,
    )


def format_command(cmd: Iterable[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)
