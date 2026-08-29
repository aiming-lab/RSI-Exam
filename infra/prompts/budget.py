#!/usr/bin/env python3
"""Report budget use to the agent.

Output tokens are reported at checkpoints; wall time only once the run is nearly over.
Silent when nothing can be measured.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

LIMIT = int(os.environ.get("ARB_OUTPUT_TOKEN_LIMIT") or 0)
TIMEOUT = float(os.environ.get("ARB_AGENT_TIMEOUT_SEC") or 0)
CHECKPOINTS = (1, 2, 4, 8, 16, 90, 95, 99)
TIME_CHECKPOINTS = (90, 95, 99)
WRAP_UP = " Wrap up soon and leave in /app/methods/main/ the version you want graded."
TOKENS_OUT = " — your output-token budget is nearly exhausted." + WRAP_UP
TIME_OUT = " — your run window is nearly over." + WRAP_UP
STATE = "/tmp/.arb_budget_band"
TIME_STATE = "/tmp/.arb_budget_time"


def codex() -> int | None:
    home = os.environ.get("CODEX_HOME", "/tmp/codex-home")
    files = sorted(glob.glob(f"{home}/sessions/**/rollout-*.jsonl", recursive=True))
    if not files:
        return None
    used = None
    for line in open(files[-1], errors="ignore"):
        if '"token_count"' not in line:
            continue
        try:
            used = json.loads(line)["payload"]["info"]["total_token_usage"]["output_tokens"]
        except Exception:
            pass
    return used


def claude_logs() -> list[str]:
    # harbor points CLAUDE_CONFIG_DIR at /logs/agent/sessions, not ~/.claude.
    roots = [os.environ.get("CLAUDE_CONFIG_DIR"), os.path.expanduser("~/.claude")]
    return [f"{r}/projects/-app/*.jsonl" for r in roots if r]


def _lines(pattern: str):
    for f in sorted(glob.glob(os.path.expanduser(pattern), recursive=True)):
        try:
            for line in open(f, errors="ignore"):
                yield line
        except OSError:
            pass


def started_at() -> dt.datetime | None:
    """Agent start = first event in the harness transcript."""
    for pat in [f"{os.environ.get('CODEX_HOME', '/tmp/codex-home')}/sessions/**/rollout-*.jsonl",
                *claude_logs()]:
        for f in sorted(glob.glob(pat, recursive=True)):
            for line in open(f, errors="ignore"):
                try:
                    ts = json.loads(line).get("timestamp")
                    if ts:
                        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    break
    # Every harness gets its stdout teed here when the agent phase starts.
    stamps = [os.path.getmtime(f) for f in glob.glob("/logs/agent/*.txt")]
    if stamps:
        return dt.datetime.fromtimestamp(min(stamps), dt.timezone.utc)
    return None


def claude() -> int | None:
    # only this task's project dir (claude-code names it after the cwd, /app)
    total = 0
    for pat in claude_logs():
        for line in _lines(pat):
            if '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
                if d.get("type") != "assistant":
                    continue
                total += (d.get("message") or {}).get("usage", {}).get("output_tokens") or 0
            except Exception:
                pass
    return total or None


def _gemini_out(msg: dict) -> int:
    t = msg.get("tokens") or {}
    return sum(t.get(k) or 0 for k in ("output", "thoughts", "tool"))


def gemini() -> int | None:
    """~/.gemini/tmp/**/session-*.json{,l}; jsonl records revise messages by id."""
    latest: dict[str, dict] = {}
    for f in sorted(glob.glob(os.path.expanduser("~/.gemini/tmp/**/session-*.json*"),
                              recursive=True)):
        try:
            text = open(f, errors="ignore").read()
        except OSError:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "messages" in data:
                for i, m in enumerate(data["messages"]):
                    latest[m.get("id") or f"{f}:{i}"] = m
                continue
        except Exception:
            pass
        for i, line in enumerate(text.splitlines()):
            try:
                r = json.loads(line)
            except Exception:
                continue
            m = r.get("message") if isinstance(r.get("message"), dict) else r
            latest[m.get("id") or f"{f}:{i}"] = m
    total = sum(_gemini_out(m) for m in latest.values() if m.get("type") == "gemini")
    return total or None


def qwen() -> int | None:
    total = 0
    for line in _lines("~/.qwen/projects/**/*.jsonl"):
        if '"usageMetadata"' not in line:
            continue
        try:
            e = json.loads(line)
            if e.get("type") != "assistant":
                continue
            u = e.get("usageMetadata") or {}
            total += (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
        except Exception:
            pass
    return total or None



def kimi() -> int | None:
    """kimi-cli tees a JSON-RPC event stream; StatusUpdate carries the turn's usage."""
    total, pending = 0, 0
    for line in _lines("/logs/agent/kimi-cli.txt"):
        if '{"jsonrpc"' not in line:
            continue
        try:
            p = json.loads(line, strict=False).get("params") or {}
        except Exception:
            continue
        etype, payload = p.get("type"), p.get("payload") or {}
        if etype == "StatusUpdate":
            pending = (payload.get("token_usage") or {}).get("output") or pending
        elif etype in ("TurnEnd", "StepBegin"):
            total, pending = total + pending, 0
    return (total + pending) or None

def _fire(state: str, marks, pct: float):
    reached = [c for c in marks if pct >= c]
    if not reached:
        return None
    mark = reached[-1]
    try:
        last = int(open(state).read())
    except Exception:
        last = 0
    if mark <= last:
        return None
    open(state, "w").write(str(mark))
    return mark


READERS = (codex, claude, gemini, qwen, kimi)


def main() -> None:
    if LIMIT > 0:
        used = None
        for reader in READERS:
            try:
                used = reader()
            except Exception:
                used = None
            if used is not None:
                break
        if used is not None:
            pct = used / LIMIT * 100
            mark = _fire(STATE, CHECKPOINTS, pct)
            if mark:
                line = f"[budget] {used:,} / {LIMIT:,} output tokens used ({pct:.1f}%)"
                if mark >= 90:
                    line += TOKENS_OUT
                elif mark <= 10:
                    line += " — nearly all of your budget is still available."
                print(line)

    if TIMEOUT > 0:
        t0 = started_at()
        if t0:
            elapsed = (dt.datetime.now(dt.timezone.utc) - t0).total_seconds()
            pct = elapsed / TIMEOUT * 100
            if _fire(TIME_STATE, TIME_CHECKPOINTS, pct):
                print(f"[budget] {elapsed / 60:.0f} / {TIMEOUT / 60:.0f} min elapsed ({pct:.1f}%)" + TIME_OUT)




if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
