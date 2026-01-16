from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastmcp.server import FastMCP
from fastmcp.server.context import Context
from fastmcp.server.dependencies import CurrentContext, Progress
from fastmcp.server.tasks import TaskConfig

from wad_mcp_server.status import WadStatus, now_rfc3339
from wad_mcp_server.wad import WadResult, format_command, run_wad, run_wad_with_status


def _result_payload(result: WadResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": result.command,
        "command_str": format_command(result.command),
        "cwd": result.cwd,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "combined": result.combined,
    }

    # Convenience: include the last status marker (if any) so clients that do not
    # subscribe to notifications can still get a machine-readable final status.
    payload["last_status"] = _extract_last_status_json(result.combined)

    return payload


def _extract_last_status_json(combined: str) -> dict[str, Any] | None:
    """Extract the last WAD_STATUS JSON object from combined output."""

    last: dict[str, Any] | None = None
    for line in combined.splitlines():
        if not line.startswith("WAD_STATUS "):
            continue
        payload = line[len("WAD_STATUS ") :].strip()
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if isinstance(obj, dict):
            last = obj
    return last


def _parse_goose_result_from_status_output(combined: str) -> Any | None:
    """Best-effort parse the JSON blob printed by `wad status` (if any)."""

    start = combined.find("{")
    if start == -1:
        return None

    maybe = combined[start:]
    try:
        return json.loads(maybe)
    except Exception:
        return None


async def _emit_status(
    *,
    ctx: Context,
    progress: Progress,
    code: str,
    state: str,
    message: str,
    step: int | None = None,
    total: int | None = None,
) -> None:
    """Emit a WadStatus update through task statusMessage + logs."""

    status = WadStatus(
        code=code,
        state=state,  # type: ignore[arg-type]
        message=message,
        step=step,
        total=total,
        ts=now_rfc3339(),
    )

    # Persist machine-readable JSON into Docket progress, which FastMCP exposes
    # as MCP task statusMessage.
    with contextlib.suppress(Exception):
        await progress.set_message(status.to_status_message())

    # Also emit a human-friendly log with structured `extra`.
    with contextlib.suppress(Exception):
        await ctx.log(
            message,
            level="info",
            logger_name="wad.status",
            extra=status.to_dict(),
        )

    # Best-effort progress notification if client provided progressToken.
    if step is not None:
        with contextlib.suppress(Exception):
            await ctx.report_progress(step, total, message)


mcp = FastMCP(
    "wad",
    instructions=(
        "Expose WAD (Worktree Agent Devcontainers) operations over MCP. "
        "Tools shell out to the `wad` bash script in the project repo."
    ),
    # Enable task support so long-running operations can be run as background tasks.
    tasks=True,
)


# --- High-level wrappers ----------------------------------------------------


@mcp.tool(
    description="Initialize WAD in the repo (creates .wad/ templates).",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
async def wad_init(repo_path: str | None = None, mode: str | None = None) -> dict[str, Any]:
    args: list[str] = ["init"]
    if mode:
        args.append(mode)
    result = await run_wad(*args, repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(
    description=(
        "Create a new isolated environment: `wad new <env> [prompt...]`. "
        "This starts containers+services and optionally starts a goose agent task."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_new(
    env: str,
    prompt: str | None = None,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    args = ["new", env]
    if prompt:
        args.append(prompt)

    # No timeout by default; docker compose may pull images.
    result = await run_wad_with_status(
        *args,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description="Start configured service apps in the devcontainer for an environment: `wad start <env>`.",
    task=TaskConfig(mode="optional"),
)
async def wad_start(
    env: str,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    result = await run_wad_with_status(
        "start",
        env,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description="Stop configured service apps in the devcontainer for an environment: `wad stop <env>`.",
    task=TaskConfig(mode="optional"),
)
async def wad_stop(
    env: str,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    result = await run_wad_with_status(
        "stop",
        env,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description=(
        "Remove an environment: `wad rm <env> --force`. "
        "WARNING: removes docker resources and git worktree."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_rm(
    env: str,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    args = ["rm", env, "--force"]
    result = await run_wad_with_status(
        *args,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description="List environments: `wad ls`.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
)
async def wad_ls(repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("ls", repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(
    description="Start configured services for an env: `wad run <env>`.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_run(
    env: str,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    result = await run_wad_with_status(
        "run",
        env,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description=(
        "Show logs: `wad logs <env> [service]`. "
        "WAD defaults to printing a bounded amount of logs and exiting (no follow), "
        "so this should be safe for unattended MCP usage."
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_logs(
    env: str,
    service: str | None = None,
    repo_path: str | None = None,
    timeout_s: float | None = 5.0,
    max_output_chars: int = 20000,
) -> dict[str, Any]:
    args = ["logs", env]
    if service:
        args.append(service)
    result = await run_wad(
        *args,
        repo_path=repo_path,
        timeout_s=timeout_s,
        max_output_chars=max_output_chars,
    )
    return _result_payload(result)


@mcp.tool(
    description="Show goose task status: `wad status <env>`.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_status(env: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("status", env, repo_path=repo_path)

    payload = _result_payload(result)

    # Best-effort parse JSON blob from wad status.
    # wad prints human text and then a JSON object if available.
    payload["parsed_json"] = _parse_goose_result_from_status_output(payload.get("combined", ""))

    return payload


@mcp.tool(
    description=(
        "Start a goose agent task in an existing env: `wad agent <env> <prompt...>`. "
        "This starts the agent in tmux (detached) and returns immediately."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_agent(
    env: str,
    prompt: str,
    repo_path: str | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    result = await run_wad_with_status(
        "agent",
        env,
        prompt,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )
    return _result_payload(result)


@mcp.tool(
    description=(
        "Start a goose agent task and wait for completion, emitting status updates as it runs. "
        "This is useful for MCP background tasks / UIs that want a single long-running task."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
    },
    task=TaskConfig(mode="optional"),
)
async def wad_agent_wait(
    env: str,
    prompt: str,
    repo_path: str | None = None,
    poll_interval_s: float = 2.0,
    timeout_s: float | None = None,
    ctx: Context = CurrentContext(),
    progress: Progress = Progress(),
) -> dict[str, Any]:
    # Phase 1: start agent (this returns quickly)
    await _emit_status(
        ctx=ctx,
        progress=progress,
        code="agent.start",
        state="starting",
        message=f"Starting goose agent for '{env}'",
        step=1,
        total=3,
    )

    start_result = await run_wad_with_status(
        "agent",
        env,
        prompt,
        ctx=ctx,
        progress=progress,
        repo_path=repo_path,
    )

    if start_result.returncode != 0:
        await _emit_status(
            ctx=ctx,
            progress=progress,
            code="agent.failed",
            state="failed",
            message="Failed to start goose agent",
            step=3,
            total=3,
        )
        payload = _result_payload(start_result)
        payload["parsed_json"] = None
        return payload

    # Phase 2: poll status until done
    await _emit_status(
        ctx=ctx,
        progress=progress,
        code="agent.running",
        state="running",
        message="Goose agent running",
        step=2,
        total=3,
    )

    start_t = asyncio.get_event_loop().time()

    while True:
        if timeout_s is not None:
            elapsed = asyncio.get_event_loop().time() - start_t
            if elapsed > timeout_s:
                await _emit_status(
                    ctx=ctx,
                    progress=progress,
                    code="agent.failed",
                    state="failed",
                    message=f"Timed out waiting for goose agent after {timeout_s}s",
                    step=3,
                    total=3,
                )
                break

        status_result = await run_wad("status", env, repo_path=repo_path)
        combined = status_result.combined

        done = "done:    yes" in combined
        running = "running: yes" in combined

        if done:
            exit_code: int | None = None
            for line in combined.splitlines():
                if line.strip().startswith("exit:"):
                    try:
                        exit_code = int(line.split(":", 1)[1].strip())
                    except Exception:
                        exit_code = None

            if exit_code == 0:
                await _emit_status(
                    ctx=ctx,
                    progress=progress,
                    code="agent.finished",
                    state="completed",
                    message="Goose agent finished successfully",
                    step=3,
                    total=3,
                )
            else:
                await _emit_status(
                    ctx=ctx,
                    progress=progress,
                    code="agent.failed",
                    state="failed",
                    message=f"Goose agent failed (exit={exit_code})",
                    step=3,
                    total=3,
                )
            break

        if running:
            # keep-alive status so UIs update timestamps
            await _emit_status(
                ctx=ctx,
                progress=progress,
                code="agent.running",
                state="running",
                message="Goose agent running",
                step=2,
                total=3,
            )

        await asyncio.sleep(poll_interval_s)

    # Return the final status payload (best-effort JSON extraction)
    final_status = await run_wad("status", env, repo_path=repo_path)
    payload = _result_payload(final_status)
    payload["parsed_json"] = _parse_goose_result_from_status_output(payload.get("combined", ""))

    return payload


def main() -> None:
    """Entrypoint for the stdio MCP server.

    Note:
    - `wad mcp` runs this module via `python -m wad_mcp_server.server` in some cases.
      That requires we start the server when executed as `__main__` (see guard below).
    - FastMCP's API has changed a bit across releases; we prefer stdio explicitly when
      the `transport=` parameter is supported.
    """

    # Stdio transport for local tool usage.
    try:
        import inspect

        if "transport" in inspect.signature(mcp.run).parameters:
            mcp.run(transport="stdio")
        else:
            mcp.run()
    except Exception:
        # Fall back to the default behavior if introspection fails.
        mcp.run()


if __name__ == "__main__":
    main()
