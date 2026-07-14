"""Tests for the Parts Catalog Co heartbeat script."""

import json
from pathlib import Path

import pytest

from scripts.parts_catalog_heartbeat import (
    HeartbeatResult,
    active_session_count,
    build_arg_parser,
    cooldown_active,
    eligible_tickets,
    format_status,
    load_state,
    main,
    record_spawn,
    run_heartbeat,
    save_state,
    select_ticket,
    session_cap_reached,
    sort_by_priority,
)


def make_issue(id_, status="todo", priority="medium", created="2026-01-01T00:00:00Z"):
    return {"id": id_, "identifier": id_.upper(), "status": status, "priority": priority, "createdAt": created}


# ── eligibility ──────────────────────────────────────────────────────────


def test_eligible_tickets_includes_todo_and_backlog():
    issues = [make_issue("a", status="todo"), make_issue("b", status="backlog")]
    assert {i["id"] for i in eligible_tickets(issues, exclude_id="")} == {"a", "b"}


def test_eligible_tickets_excludes_other_statuses():
    issues = [
        make_issue("a", status="in_progress"),
        make_issue("b", status="blocked"),
        make_issue("c", status="done"),
        make_issue("d", status="cancelled"),
    ]
    assert eligible_tickets(issues, exclude_id="") == []


def test_eligible_tickets_excludes_self():
    issues = [make_issue("self", status="todo"), make_issue("other", status="todo")]
    result = eligible_tickets(issues, exclude_id="self")
    assert [i["id"] for i in result] == ["other"]


# ── priority sort ────────────────────────────────────────────────────────


def test_sort_by_priority_orders_urgent_first():
    issues = [
        make_issue("low", priority="low"),
        make_issue("urgent", priority="urgent"),
        make_issue("medium", priority="medium"),
        make_issue("high", priority="high"),
    ]
    ordered = [i["id"] for i in sort_by_priority(issues)]
    assert ordered == ["urgent", "high", "medium", "low"]


def test_sort_by_priority_breaks_ties_by_created_at():
    issues = [
        make_issue("newer", priority="high", created="2026-02-01T00:00:00Z"),
        make_issue("older", priority="high", created="2026-01-01T00:00:00Z"),
    ]
    ordered = [i["id"] for i in sort_by_priority(issues)]
    assert ordered == ["older", "newer"]


def test_sort_by_priority_unknown_priority_sorts_last():
    issues = [make_issue("weird", priority="banana"), make_issue("normal", priority="low")]
    ordered = [i["id"] for i in sort_by_priority(issues)]
    assert ordered == ["normal", "weird"]


def test_select_ticket_returns_none_when_no_candidates():
    assert select_ticket([], exclude_id="") is None
    assert select_ticket([make_issue("a", status="done")], exclude_id="") is None


def test_select_ticket_returns_highest_priority_eligible():
    issues = [
        make_issue("self", status="todo", priority="urgent"),
        make_issue("b", status="todo", priority="high"),
        make_issue("c", status="backlog", priority="medium"),
    ]
    picked = select_ticket(issues, exclude_id="self")
    assert picked["id"] == "b"


# ── session cap ──────────────────────────────────────────────────────────


def test_active_session_count_counts_in_progress_only():
    issues = [
        make_issue("a", status="in_progress"),
        make_issue("b", status="in_progress"),
        make_issue("c", status="todo"),
    ]
    assert active_session_count(issues) == 2


def test_session_cap_reached_true_at_cap():
    issues = [make_issue("a", status="in_progress"), make_issue("b", status="in_progress")]
    assert session_cap_reached(issues, cap=2) is True


def test_session_cap_reached_false_below_cap():
    issues = [make_issue("a", status="in_progress")]
    assert session_cap_reached(issues, cap=2) is False


def test_run_heartbeat_skips_when_session_cap_reached():
    issues = [
        make_issue("a", status="in_progress"),
        make_issue("b", status="in_progress"),
        make_issue("c", status="todo"),
    ]
    result = run_heartbeat(issues=issues, self_ticket_id="", state={}, session_cap=2)
    assert result == HeartbeatResult(picked=None, reason="session_cap_reached")


# ── cooldown ─────────────────────────────────────────────────────────────


def test_cooldown_active_true_within_window():
    state = {"spawns": {"a": 1000.0}}
    assert cooldown_active(state, "a", cooldown_seconds=300, now=1100.0) is True


def test_cooldown_active_false_after_window():
    state = {"spawns": {"a": 1000.0}}
    assert cooldown_active(state, "a", cooldown_seconds=300, now=1400.0) is False


def test_cooldown_active_false_when_never_spawned():
    assert cooldown_active({}, "a", cooldown_seconds=300, now=1000.0) is False


def test_record_spawn_sets_timestamp():
    state = {}
    record_spawn(state, "a", now=42.0)
    assert state["spawns"]["a"] == 42.0


def test_run_heartbeat_respects_cooldown():
    issues = [make_issue("a", status="todo")]
    state = {"spawns": {"a": 1000.0}}
    result = run_heartbeat(
        issues=issues, self_ticket_id="", state=state, now=1100.0, cooldown_seconds=300
    )
    assert result.reason == "cooldown_active"
    assert result.spawned is False


def test_load_state_missing_file_returns_default(tmp_path: Path):
    assert load_state(tmp_path / "missing.json") == {"spawns": {}}


def test_load_state_corrupt_file_returns_default(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert load_state(path) == {"spawns": {}}


def test_save_and_load_state_roundtrip(tmp_path: Path):
    path = tmp_path / "nested" / "state.json"
    save_state(path, {"spawns": {"a": 5.0}})
    assert load_state(path) == {"spawns": {"a": 5.0}}


# ── spawn ────────────────────────────────────────────────────────────────


def test_run_heartbeat_dry_run_does_not_spawn():
    issues = [make_issue("a", status="todo")]
    spawned_tickets = []
    result = run_heartbeat(
        issues=issues,
        self_ticket_id="",
        state={},
        dry_run=True,
        spawn_fn=lambda t: spawned_tickets.append(t["id"]),
    )
    assert result.reason == "dry_run"
    assert result.spawned is False
    assert spawned_tickets == []


def test_run_heartbeat_spawns_and_records_cooldown():
    issues = [make_issue("a", status="todo")]
    state = {}
    spawned_tickets = []
    result = run_heartbeat(
        issues=issues,
        self_ticket_id="",
        state=state,
        now=1000.0,
        spawn_fn=lambda t: spawned_tickets.append(t["id"]),
    )
    assert result.reason == "spawned"
    assert result.spawned is True
    assert spawned_tickets == ["a"]
    assert state["spawns"]["a"] == 1000.0


def test_run_heartbeat_no_eligible_tickets():
    result = run_heartbeat(issues=[], self_ticket_id="", state={})
    assert result == HeartbeatResult(picked=None, reason="no_eligible_tickets")


def test_run_heartbeat_excludes_self_ticket():
    issues = [make_issue("self", status="todo")]
    result = run_heartbeat(issues=issues, self_ticket_id="self", state={})
    assert result.reason == "no_eligible_tickets"


# ── status display ───────────────────────────────────────────────────────


def test_format_status_no_spawns():
    issues = [make_issue("a", status="in_progress")]
    output = format_status(issues, {}, session_cap=2, cooldown_seconds=300)
    assert "Session usage: 1/2" in output
    assert "Recent spawns: none" in output


def test_format_status_shows_active_cooldown():
    issues = []
    state = {"spawns": {"a": 1000.0}}
    output = format_status(
        issues, state, session_cap=2, cooldown_seconds=300, now=1100.0
    )
    assert "a: cooldown 200s remaining" in output


def test_format_status_shows_expired_cooldown():
    issues = []
    state = {"spawns": {"a": 1000.0}}
    output = format_status(
        issues, state, session_cap=2, cooldown_seconds=300, now=2000.0
    )
    assert "a: cooldown expired" in output


def test_format_status_counts_eligible_tickets():
    issues = [make_issue("a", status="todo"), make_issue("b", status="backlog"), make_issue("c", status="done")]
    output = format_status(issues, {}, session_cap=2, cooldown_seconds=300)
    assert "Eligible tickets: 2" in output


# ── CLI flags ────────────────────────────────────────────────────────────


def test_arg_parser_requires_company_id():
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_arg_parser_defaults():
    parser = build_arg_parser()
    args = parser.parse_args(["--company-id", "abc"])
    assert args.dry_run is False
    assert args.status is False
    assert args.session_cap == 2
    assert args.cooldown_seconds == 300
    assert args.self_ticket_id == ""


def test_arg_parser_dry_run_and_status_flags():
    parser = build_arg_parser()
    args = parser.parse_args(["--company-id", "abc", "--dry-run", "--status"])
    assert args.dry_run is True
    assert args.status is True


def test_arg_parser_overrides():
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--company-id",
            "abc",
            "--self-ticket-id",
            "self-1",
            "--session-cap",
            "5",
            "--cooldown-seconds",
            "60",
            "--api-base",
            "http://example.test",
        ]
    )
    assert args.self_ticket_id == "self-1"
    assert args.session_cap == 5
    assert args.cooldown_seconds == 60
    assert args.api_base == "http://example.test"


def test_main_dry_run_reports_pick_without_spawning(monkeypatch, tmp_path, capsys):
    issues = [make_issue("a", status="todo")]

    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.list_company_issues",
        lambda self, company_id: issues,
    )
    checkout_calls = []
    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.checkout_issue",
        lambda self, issue_id: checkout_calls.append(issue_id),
    )

    state_file = tmp_path / "state.json"
    exit_code = main(["--company-id", "co-1", "--dry-run", "--state-file", str(state_file)])

    assert exit_code == 0
    assert checkout_calls == []
    assert not state_file.exists()
    captured = capsys.readouterr()
    assert "dry_run: A" in captured.out


def test_main_spawns_and_persists_state(monkeypatch, tmp_path, capsys):
    issues = [make_issue("a", status="todo")]

    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.list_company_issues",
        lambda self, company_id: issues,
    )
    checkout_calls = []
    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.checkout_issue",
        lambda self, issue_id: checkout_calls.append(issue_id),
    )

    state_file = tmp_path / "state.json"
    exit_code = main(["--company-id", "co-1", "--state-file", str(state_file)])

    assert exit_code == 0
    assert checkout_calls == ["a"]
    assert json.loads(state_file.read_text())["spawns"]["a"] > 0
    captured = capsys.readouterr()
    assert "spawned: A" in captured.out


def test_main_status_flag_prints_status_and_skips_spawn(monkeypatch, tmp_path, capsys):
    issues = [make_issue("a", status="in_progress")]

    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.list_company_issues",
        lambda self, company_id: issues,
    )
    checkout_calls = []
    monkeypatch.setattr(
        "scripts.parts_catalog_heartbeat.PaperclipClient.checkout_issue",
        lambda self, issue_id: checkout_calls.append(issue_id),
    )

    state_file = tmp_path / "state.json"
    exit_code = main(["--company-id", "co-1", "--status", "--state-file", str(state_file)])

    assert exit_code == 0
    assert checkout_calls == []
    captured = capsys.readouterr()
    assert "Session usage: 1/2" in captured.out
