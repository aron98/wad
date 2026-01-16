from __future__ import annotations

import json
from typing import Any

from fastmcp.server import FastMCP
from fastmcp.server.tasks import TaskConfig

from wad_mcp_server.wad import WadResult, format_command, run_wad


def _result_payload(result: WadResult) -> dict[str, Any]:
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": result.command,
        "command_str": format_command(result.command),
        "cwd": result.cwd,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "combined": result.combined,
    }


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
        "idempotentHint": True
    }
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
        "idempotentHint": True
    },
    task=TaskConfig(mode="optional"),
)
async def wad_new(
    env: str,
    prompt: str | None = None,
    repo_path: str | None = None,
) -> dict[str, Any]:
    args = ["new", env]
    if prompt:
        args.append(prompt)
    # No timeout by default; docker compose may pull images.
    result = await run_wad(*args, repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(description="Start configured service apps in the devcontainer for an environment: `wad start <env>`.", task=TaskConfig(mode="optional"))
async def wad_start(env: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("start", env, repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(description="Stop onfigured service apps in the devcontainer for an environment: `wad stop <env>`.", task=TaskConfig(mode="optional"))
async def wad_stop(env: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("stop", env, repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(
    description=(
        "Remove an environment: `wad rm <env> --force`. "
        "WARNING: removes docker resources and git worktree."
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True
    },
    task=TaskConfig(mode="optional"),

)
async def wad_rm(env: str, repo_path: str | None = None) -> dict[str, Any]:
    args = ["rm", env, "--force"]
    result = await run_wad(*args, repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(
    description="List environments: `wad ls`.",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True
    },
)
async def wad_ls(repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("ls", repo_path=repo_path)
    return _result_payload(result)


@mcp.tool(
    description="Start configured services for an env: `wad run <env>`.", task=TaskConfig(mode="optional"),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True
    },
)
async def wad_run(env: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("run", env, repo_path=repo_path)
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
        "idempotentHint": True
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
        "idempotentHint": True
    },
    task=TaskConfig(mode="optional")
)
async def wad_status(env: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("status", env, repo_path=repo_path)

    payload = _result_payload(result)

    # Best-effort parse JSON blob from wad status.
    # wad prints human text and then a JSON object if available.
    combined = payload.get("combined", "")
    json_obj: Any | None = None
    start = combined.find("{")
    if start != -1:
        maybe = combined[start:]
        try:
            json_obj = json.loads(maybe)
        except Exception:
            json_obj = None
    payload["parsed_json"] = json_obj

    return payload


@mcp.tool(
    description="Start a goose agent task in an existing env: `wad agent <env> <prompt...>`.",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False
    },
    task=TaskConfig(mode="optional"),
)
async def wad_agent(env: str, prompt: str, repo_path: str | None = None) -> dict[str, Any]:
    result = await run_wad("agent", env, prompt, repo_path=repo_path)
    return _result_payload(result)


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
