#!/usr/bin/env bash
# Let harbor's antigravity-cli adapter run long tasks (patch M3, 2026-08-17)
#
# -- In one line ------------------------------------------------------------
# Add --print-timeout (default 12h) to antigravity_cli.py's CLI_FLAGS, and
# expose --output-format while we are there. That is all.
#
# -- The problem ------------------------------------------------------------
# harbor drives agy through print mode (`agy --prompt=...`). agy's print mode
# carries a timeout of its own:
#
#     --print-timeout   Timeout for print mode wait (default 5m0s)
#
# harbor's CLI_FLAGS holds only --sandbox, so the flag never reaches the
# command line and agy falls back to its own 5-minute default. **Any task
# longer than five minutes is cut off mid-run**, and because the process exits
# cleanly harbor proceeds to grading as usual -- half-finished work is graded,
# the reward collapses, and nothing reports an error.
#
# Measured (same prompt, told to sleep 420 then answer; this flag the only
# difference):
#     omitted              5m01s  exit 1  Error: timeout waiting for response
#     --print-timeout 30m  7m10s  exit 0  DONE_LONG
#
# Our tasks run on a 12h budget, so this is not a limitation -- it is
# unusable.
#
# Upgrading does not help: a full search of the 0.20.0, 0.21.0 and
# 0.21.1.dev202608170007 wheels finds neither `print-timeout` nor
# `print_timeout`. `--ak print_timeout=` does not work either -- build_cli_flags()
# only walks flags declared in CLI_FLAGS and silently ignores the rest.
#
# -- Why a default instead of passing --ak every time -----------------------
# Three sibling traps in a single day: codex leaves web_search on unless told
# otherwise, gemini-cli silently substitutes 3.5-flash for an unlisted --model,
# agy times out at 5 minutes. All the same shape: harbor's CliFlag has no
# default -> the argument never appears -> the other side's default wins -> no
# error. So this sets default="12h" and makes the common case correct.
# Overriding still works:
#     --ak print_timeout=2h            (highest precedence)
#     --ae AGY_PRINT_TIMEOUT=2h        (env_fallback)
#
# -- Why --output-format comes along ----------------------------------------
# Optional, and the default stays agy's own `text`. It is exposed because
# `--output-format stream-json` yields two things available nowhere else
# (measured):
#
#   1. Per-step token usage, and the totals in the closing result event:
#        {"event":"step_update", ..., "usage":{"input_tokens":92,"output_tokens":5,
#         "thinking_tokens":0,"cache_read_tokens":0,"total_tokens":97}}
#      agy writes no usage to disk at all (not even in its session SQLite
#      database), so this is the only source.
#      Note this alone is not enough: budget.py currently reads only codex
#      rollouts and claude-code project logs, and would need work to consume
#      agy's format.
#
#   2. The init event records **the model that actually served the run**:
#        {"event":"init", ..., "init":{"model":"gemini-3.7-flash-high", ...}}
#      The gemini-cli substitution above went unnoticed for three tasks purely
#      because no such run-time record existed.
#
# The cost: stdout turns from human-readable text into a JSON event stream, and
# /logs/agent/antigravity-cli.txt follows. harbor parses trajectories from the
# separate antigravity-cli.trajectory.jsonl and never touches stdout, so its own
# parsing is unaffected. Off by default; pass it explicitly:
#     --ak output_format=stream-json
set -uo pipefail

PY="$(command -v harbor >/dev/null 2>&1 && \
      dirname "$(readlink -f "$(command -v harbor)")")/python3"
[ -x "$PY" ] || PY=python3

TARGET="$("$PY" - <<'EOF'
import pathlib
try:
    import harbor.agents.installed.antigravity_cli as m
    print(pathlib.Path(m.__file__))
except Exception:
    print("")
EOF
)"

if [ -z "$TARGET" ] || [ ! -f "$TARGET" ]; then
  echo "M3: cannot locate harbor's antigravity_cli.py" >&2
  exit 1
fi

"$PY" - "$TARGET" <<'EOF'
import pathlib, re, sys

p = pathlib.Path(sys.argv[1])
s = p.read_text()

if "print_timeout" in s:
    print(f"M3: already patched ({p})")
    sys.exit(0)

old = '''    CLI_FLAGS = [
        CliFlag(
            "sandbox",
            cli="--sandbox",
            type="bool",
        ),
    ]'''

new = '''    CLI_FLAGS = [
        CliFlag(
            "sandbox",
            cli="--sandbox",
            type="bool",
        ),
        # agy's print mode times out after 5m unless told otherwise, which cuts
        # every long task off mid-run and still exits 0 -- see ARB patch M3.
        CliFlag(
            "print_timeout",
            cli="--print-timeout",
            type="str",
            env_fallback="AGY_PRINT_TIMEOUT",
            default="12h",
        ),
        # Opt-in: stream-json is the only place agy reports token usage, and its
        # init event records the model that actually served the run.
        CliFlag(
            "output_format",
            cli="--output-format",
            type="str",
            choices=["text", "json", "stream-json"],
        ),
    ]'''

if old not in s:
    print("M3: CLI_FLAGS block not found -- harbor changed shape, patch by hand", file=sys.stderr)
    sys.exit(1)

p.with_suffix(".py.arb-m3-backup").write_text(s)
p.write_text(s.replace(old, new, 1))
print(f"M3: patched {p}")
EOF
rc=$?
[ $rc -ne 0 ] && exit $rc

"$PY" - <<'EOF'
import importlib, harbor.agents.installed.antigravity_cli as m
importlib.reload(m)
flags = {f.kwarg: f.default for f in m.AntigravityCli.CLI_FLAGS}
print(f"M3: CLI_FLAGS now {flags}")
assert "print_timeout" in flags, "print_timeout missing after patch"
assert flags["print_timeout"] == "12h", "print_timeout default not 12h"
EOF
