# Network Policy

A task's network policy is **three rules for one container across three phases**, and all three
have to be written out explicitly.

```
docker build ─┬─ env up ─┬─ install agent ─┬─ agent works ─┬─ grading ─┐
              │          │                 │               │           │
  not covered ┘   [environment] ───────────┤    [agent] ───┤ [verifier]
```

The build phase (`RUN` in a Dockerfile) goes over docker's default bridge and **none of the three
rules reach it**. Data and dependencies are baked into the image here — that is the legitimate,
and only, time to download.

---

## The default

```toml
[environment]
network_mode = "public"          # harbor installs codex / claude-code in this phase

[agent]
network_mode = "no-network"      # the model endpoint is added at run time

[verifier]
environment_mode = "separate"
[verifier.environment]
network_mode = "no-network"
```

---

## `[agent]` special case: the task itself calls a model API

Some tasks have **task code** that calls an LLM — a judge, or the base model of a memory system
being optimised.

**The endpoint is never written into the task.** `allowed_hosts` takes literal hostnames and does
**no `${VAR}` interpolation** (measured: `${MEMORY_LLM_HOST}` is rejected outright by the
validator). Hard-coding one would bake our provider into a public task bank, and anyone with a
different endpoint would have to edit the task.

So the task still declares `no-network`, and the endpoint is **derived at run time** from the URL
in `.env.local`:

```toml
[agent]
network_mode = "no-network"   # endpoint added at run time; the task assumes no provider

[environment.env]
MEMORY_LLM_API_KEY  = "${MEMORY_LLM_API_KEY}"                          # no default -> fails loudly if unset
MEMORY_LLM_API_BASE = "${MEMORY_LLM_API_BASE:-https://api.openai.com/v1}"
```

```bash
set -a; . .env.local; set +a
HOST=$(python3 -c "import os,urllib.parse as u; print(u.urlparse(os.environ['MEMORY_LLM_API_BASE']).hostname)")

harbor run -p <task> ... --env-file .env.local --allow-agent-host "$HOST"
```

The allowlist and the URL the task actually dials now come from the same place, so they cannot
drift. Switching provider is one line in `.env.local`; the task is untouched.

`resolve_env_vars` passes through only the keys the task names, so **anything in `.env.local` the
task did not declare never enters the container** (measured: `OTHER_TASK_KEY` from the same
`.env.local` is ABSENT inside). A superset `.env.local` is therefore safe.

⚠ **An empty value does not fall back.** harbor tests `if var_name in os.environ` — presence, not
value. `MEMORY_LLM_API_BASE=` with nothing after it yields an empty string in the container, not
the default.

⚠ **Do not write `env-overlay/docker-compose.yaml`.** That was a workaround for an old bug. Since
harbor 0.20 it generates `docker-compose-environment.json` itself, injecting `main`'s
`environment:` **after** `--extra-docker-compose`, so nothing is dropped and nothing is overridden.

When a task needs its own sidecar service (a grader, an inference proxy), put it in
`<task>/environment/docker-compose.yaml` — harbor reads that natively, `--project-directory` is
always `<task>/environment`, and a build context can just be written as `../xxx`. No extra flag.

---

## `[verifier]` special case: the grader needs network

⚠ **There is no run-time entry point on the grading side; it has to go in the task.** harbor has
`--allow-agent-host` and `--allow-environment-host` but **no `--allow-verifier-host`** — and once a
task declares `[verifier.environment]`, `_verifier_inherits_task_environment()` returns False, so
`--allow-environment-host` cannot reach it either.

So a task whose grader calls an API (rerunning the submission, an LLM judge) has to hard-code it:

```toml
[verifier.environment]
network_mode  = "allowlist"
allowed_hosts = ["api.openai.com"]   # the public endpoint from the task's own default; changing provider means editing this line
```

Write **the public endpoint from the task's own `${VAR:-...}` default**, not our machine's
provider. Anyone using a different endpoint must edit this line — a current harbor limitation with
no way around it. Say so in a comment in the task.

When the grader does not need network, it stays `no-network`. That is still the default.

---

## Installing the agent CLI runs under `[environment]`, not `[agent]`

harbor installs the CLI inside the agent container (codex: `apt-get install curl ripgrep` plus
`npm install -g @openai/codex`; claude-code: `apt-get install curl procps` plus
`downloads.claude.ai`; gemini/qwen/opencode: nvm over `raw.githubusercontent.com`).

**That step runs under `[environment]`'s policy**, and has nothing to do with `[agent]`:

- in `trial.py::_prepare()`, `_setup_agent()` runs **before** `agent.run()`;
- the agent environment is built from `agent_env_baseline`, i.e. `[environment]`;
- `[agent]` is applied temporarily for the duration of `_run_agent_phase` and restored afterwards.

So the default above — `[environment] = public` plus `[agent] = no-network` — is self-consistent:
open during install, sealed once the agent starts.

Measured 2026-08-12 (harbor 0.20.0, `codex-sealed-smoke`, `[agent] no-network`): `trial.log` shows
`curl https://raw.githubusercontent.com/nvm-sh/...` and `npm install -g @openai/codex` both
succeeding — neither host being on the `--allow-agent-host` list — after which the agent phase
probing github.com gets `blocked`.

⚠ **The converse does not hold.** If `[agent]` says `public` (or is omitted and inherits a public
baseline), `--allow-agent-host` is **ignored with a warning** and the agent phase runs wide open.
See the merge rules below.

### Still pre-install it in `environment/Dockerfile`

Not because the install would fail, but because every rerun otherwise pulls from npm/github again —
and once `command -v codex` short-circuits, `[environment]` can be narrowed down from `public`.

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep curl bash nodejs npm ca-certificates procps \
 && rm -rf /var/lib/apt/lists/*
```

`procps` is for claude-code: it reaps its process tree with `ps`/`pgrep` and fails strangely
without them.

---

## Writing the allowlist

The gost proxy in the egress sidecar is transparent and matches domains by the SNI of the TLS
handshake, so what you write has to be the domain the client actually dials.

**Never widen to a parent domain:**

| Write this | Not this | Because the parent also covers |
|---|---|---|
| `generativelanguage.googleapis.com` | `.googleapis.com` | `storage.googleapis.com` (hosts public datasets) |
| `.bedrock-runtime.amazonaws.com` | `.amazonaws.com` | S3 |

Azure splits by resource subdomain; match the host in `API_BASE` exactly.

**Never on any list** (public sources of held-out labels): `github.com`,
`raw.githubusercontent.com`, `huggingface.co`, `zenodo.org`, `kaggle.com`,
`*.blob.core.windows.net`.

---

## `--allow-agent-host` merge rules

| `[agent]` says | what the command-line hosts do |
|---|---|
| `no-network` | applied — promoted to an allowlist containing exactly what you passed |
| `allowlist` + hosts | applied — merged, task first, command line second, deduplicated |
| `public` | ❌ ignored, with a warning |

```python
# harbor/trial/network_policy.py::merge_extra_allowlists
if policy.network_mode == NetworkMode.PUBLIC:
    warnings.warn("... ignored because the effective network policy is public")
    return policy
allowed_hosts = list(dict.fromkeys([*policy.allowed_hosts, *extra_allowed_hosts]))
```

Which is why model endpoints are supplied at run time rather than baked into the task:

```bash
harbor run -p <task> -a codex        --allow-agent-host "*.openai.com"    --allow-agent-host openai.com
harbor run -p <task> -a claude-code  --allow-agent-host "*.anthropic.com" --allow-agent-host anthropic.com
```

The boundary matches the run. Adding a harness is one line in the batch script, not a rewrite of
every `task.toml`.
