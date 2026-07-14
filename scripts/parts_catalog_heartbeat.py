"""Parts Catalog Co heartbeat: scan the backlog and pick up the highest-priority
eligible ticket within the company's session cap.

Replaces the legacy scripts/company_heartbeat.py cron (nexus-core), which
scanned every company; this version is scoped to a single company and talks
to Paperclip's local HTTP API directly (no external HTTP dependency, matching
this repo's stdlib-only convention).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_BASE = "http://127.0.0.1:3100"
DEFAULT_SESSION_CAP = 2
DEFAULT_COOLDOWN_SECONDS = 300
DEFAULT_STATE_FILE = Path.home() / ".cache" / "parts_catalog_heartbeat_state.json"

ELIGIBLE_STATUSES = {"todo", "backlog"}
ACTIVE_STATUSES = {"in_progress"}

PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


def priority_rank(issue: dict[str, Any]) -> tuple[int, str]:
    priority = issue.get("priority") or "medium"
    return (PRIORITY_ORDER.get(priority, len(PRIORITY_ORDER)), issue.get("createdAt") or "")


def sort_by_priority(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(issues, key=priority_rank)


def eligible_tickets(issues: list[dict[str, Any]], *, exclude_id: str) -> list[dict[str, Any]]:
    return [
        issue
        for issue in issues
        if issue.get("status") in ELIGIBLE_STATUSES and issue.get("id") != exclude_id
    ]


def select_ticket(issues: list[dict[str, Any]], *, exclude_id: str) -> dict[str, Any] | None:
    candidates = sort_by_priority(eligible_tickets(issues, exclude_id=exclude_id))
    return candidates[0] if candidates else None


def active_session_count(issues: list[dict[str, Any]]) -> int:
    return sum(1 for issue in issues if issue.get("status") in ACTIVE_STATUSES)


def session_cap_reached(issues: list[dict[str, Any]], *, cap: int) -> bool:
    return active_session_count(issues) >= cap


def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {"spawns": {}}
    try:
        return json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {"spawns": {}}


def save_state(state_file: Path, state: dict[str, Any]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2))


def cooldown_active(
    state: dict[str, Any], ticket_id: str, *, cooldown_seconds: int, now: float
) -> bool:
    last = state.get("spawns", {}).get(ticket_id)
    if last is None:
        return False
    return (now - last) < cooldown_seconds


def record_spawn(state: dict[str, Any], ticket_id: str, *, now: float) -> None:
    state.setdefault("spawns", {})[ticket_id] = now


class PaperclipClient:
    """Thin stdlib-only wrapper around Paperclip's local HTTP API."""

    def __init__(self, base_url: str = DEFAULT_API_BASE, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str) -> Any:
        req = urllib.request.Request(f"{self.base_url}{path}", method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def list_company_issues(self, company_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/companies/{company_id}/issues?limit=100")

    def checkout_issue(self, issue_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/issues/{issue_id}/checkout")


@dataclass
class HeartbeatResult:
    picked: dict[str, Any] | None
    reason: str
    spawned: bool = False


def run_heartbeat(
    *,
    issues: list[dict[str, Any]],
    self_ticket_id: str,
    state: dict[str, Any],
    session_cap: int = DEFAULT_SESSION_CAP,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    now: float | None = None,
    dry_run: bool = False,
    spawn_fn=None,
) -> HeartbeatResult:
    now = now if now is not None else time.time()

    if session_cap_reached(issues, cap=session_cap):
        return HeartbeatResult(picked=None, reason="session_cap_reached")

    ticket = select_ticket(issues, exclude_id=self_ticket_id)
    if ticket is None:
        return HeartbeatResult(picked=None, reason="no_eligible_tickets")

    ticket_id = ticket["id"]
    if cooldown_active(state, ticket_id, cooldown_seconds=cooldown_seconds, now=now):
        return HeartbeatResult(picked=ticket, reason="cooldown_active")

    if dry_run:
        return HeartbeatResult(picked=ticket, reason="dry_run")

    if spawn_fn is not None:
        spawn_fn(ticket)
    record_spawn(state, ticket_id, now=now)
    return HeartbeatResult(picked=ticket, reason="spawned", spawned=True)


def format_status(
    issues: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    session_cap: int,
    cooldown_seconds: int,
    now: float | None = None,
) -> str:
    now = now if now is not None else time.time()
    active = active_session_count(issues)
    lines = [
        f"Session usage: {active}/{session_cap}",
        f"Eligible tickets: {len(eligible_tickets(issues, exclude_id=''))}",
    ]
    spawns = state.get("spawns", {})
    if not spawns:
        lines.append("Recent spawns: none")
        return "\n".join(lines)

    lines.append("Recent spawns:")
    for ticket_id, ts in spawns.items():
        remaining = cooldown_seconds - (now - ts)
        if remaining > 0:
            lines.append(f"  {ticket_id}: cooldown {remaining:.0f}s remaining")
        else:
            lines.append(f"  {ticket_id}: cooldown expired")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parts Catalog Co heartbeat: scan backlog, pick up eligible tickets."
    )
    parser.add_argument("--company-id", required=True, help="Paperclip company ID")
    parser.add_argument(
        "--self-ticket-id",
        default="",
        help="This heartbeat's own issue ID, excluded from selection",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Scan and report without spawning"
    )
    parser.add_argument(
        "--status", action="store_true", help="Print session/cooldown status and exit"
    )
    parser.add_argument("--session-cap", type=int, default=DEFAULT_SESSION_CAP)
    parser.add_argument("--cooldown-seconds", type=int, default=DEFAULT_COOLDOWN_SECONDS)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    client = PaperclipClient(base_url=args.api_base)
    try:
        issues = client.list_company_issues(args.company_id)
    except urllib.error.URLError as exc:
        print(f"error: could not reach Paperclip API at {args.api_base}: {exc}")
        return 1

    state = load_state(args.state_file)

    if args.status:
        print(
            format_status(
                issues,
                state,
                session_cap=args.session_cap,
                cooldown_seconds=args.cooldown_seconds,
            )
        )
        return 0

    result = run_heartbeat(
        issues=issues,
        self_ticket_id=args.self_ticket_id,
        state=state,
        session_cap=args.session_cap,
        cooldown_seconds=args.cooldown_seconds,
        dry_run=args.dry_run,
        spawn_fn=lambda ticket: client.checkout_issue(ticket["id"]),
    )

    label = result.picked.get("identifier", result.picked.get("id")) if result.picked else "none"
    print(f"{result.reason}: {label}")

    if result.spawned:
        save_state(args.state_file, state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
