from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


# NOTE: MCP task status messages are plain strings (SEP-1686 statusMessage).
# We embed a JSON object in that string so clients can parse it.

StatusState = Literal[
    "starting",
    "running",
    "completed",
    "failed",
]


@dataclass(frozen=True)
class WadStatus:
    """A machine-readable status update for long-running WAD operations."""

    code: str
    state: StatusState
    message: str

    # Optional progress metadata (step-based, not time-based).
    step: int | None = None
    total: int | None = None

    # RFC3339 timestamp (server-side) for clients that want ordering.
    ts: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "namespace": "wad",
            "code": self.code,
            "state": self.state,
            "message": self.message,
        }
        if self.step is not None:
            d["step"] = self.step
        if self.total is not None:
            d["total"] = self.total
        if self.ts is not None:
            d["ts"] = self.ts
        return d

    def to_status_message(self) -> str:
        """Serialize to the string stored in MCP task statusMessage."""

        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_wad_status_line(line: str) -> WadStatus | None:
    """Parse a status marker line emitted by the `wad` bash script.

    Expected format:
      WAD_STATUS {"code":"...","state":"...","message":"..."...}

    Returns None if the line is not a status marker.
    """

    prefix = "WAD_STATUS "
    if not line.startswith(prefix):
        return None

    payload = line[len(prefix) :].strip()
    if not payload:
        return None

    try:
        obj = json.loads(payload)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    code = obj.get("code")
    state = obj.get("state")
    message = obj.get("message")

    if not isinstance(code, str) or not isinstance(state, str) or not isinstance(message, str):
        return None

    step = obj.get("step")
    total = obj.get("total")
    ts = obj.get("ts")

    return WadStatus(
        code=code,
        state=state,  # type: ignore[arg-type]
        message=message,
        step=step if isinstance(step, int) else None,
        total=total if isinstance(total, int) else None,
        ts=ts if isinstance(ts, str) else None,
    )
