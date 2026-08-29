<p align="center">
  <img src="assets/logo.jpg" width="330" alt="RSI-Exam">
</p>

<h3 align="center">Benchmarking Recursive Self-Improvement through Executable Research</h3>

<p align="center">
  Can frontier AI agents achieve Recursive Self-Improvement by turning a weak method into one that performs better on hidden data?
</p>

<p align="center">
  <a href="https://rsi-exam.ai"><img src="https://img.shields.io/badge/Website-rsi--exam.ai-2c5f5d" alt="Website"></a>
  <a href="https://huggingface.co/datasets/AIMING-Lab-UNC/RSI-Exam"><img src="https://img.shields.io/badge/%F0%9F%A4%97%20HuggingFace-RSI--Exam-ffcc4d" alt="HuggingFace"></a>
  <a href="https://discord.gg/FBzhepyE"><img src="https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
</p>

---

**This repository is the evaluation infrastructure for RSI-Exam.** It runs on
[harbor](https://www.harborframework.com/), which provides the sandbox, the agent/grader image
split, and grading. What we add on top is the autoresearch protocol given to the agent, plus the
network policy and per-harness overlays that seal the run.

**The tasks live on HuggingFace.** The 35 public ones, each with its complete grading
container, are at
[🤗 AIMING-Lab-UNC/RSI-Exam](https://huggingface.co/datasets/AIMING-Lab-UNC/RSI-Exam); the
remaining 53 are held back. Download them into `tasks/`, then pass a task directory to
`harbor run`.

📮 **To evaluate on the full 88-task suite**, contact
[contact@rsi-exam.ai](mailto:contact@rsi-exam.ai).

💬 **To get involved**, join the discussion on [Discord](https://discord.gg/FBzhepyE), or our
WeChat group.

<details>
<summary><b>WeChat group</b> — click to show the QR code</summary>
<br>
<p align="center">
  <img src="assets/wechat-group.jpg" width="240" alt="WeChat group QR code">
</p>
</details>

## 🔥 News

- **2026-08-28** — Data and code live: the public task set on
  [🤗 AIMING-Lab-UNC/RSI-Exam](https://huggingface.co/datasets/AIMING-Lab-UNC/RSI-Exam),
  and this evaluation infrastructure on GitHub.
- **2026-08-26** — Website live: [rsi-exam.ai](https://rsi-exam.ai) — the 88-task leaderboard
  (Full / Public 35 / Private 53), per-domain task pages, the evaluation pipeline, three
  trajectory case studies, and the authoring guide.

## 🤔 What Is RSI-Exam

RSI-Exam evaluates whether an AI agent can **improve itself over a long horizon and generalize to
unseen data**. Each task hands it a working but weak method and lets it experiment for up to 12
hours against a visible split. Whatever it submits is then replayed once, from scratch, on a sealed
split it never touched — and that single number is the score. **An improvement that does not
transfer earns nothing.**

### How an evaluation works

Two images, one boundary: the agent iterates in its own container, and the only thing that crosses
is the artifact it submits. A fresh container reruns it on hidden data and normalises the result
against anchors measured in advance — baseline 0, frontier-calibrated reference 0.6 (where one
exists), upper bound 1.

<p align="center">
  <img src="assets/framework.png" width="900" alt="The agent iterates on visible data; one artifact crosses into a sealed offline verifier, which reruns it on hidden data and returns a normalised score">
</p>

### Task taxonomy

The full benchmark holds **88 active tasks across six domains**. 35 are public, with their complete
grading containers; the other 53 are held back.

<p align="center">
  <img src="assets/task-bank.png" width="900" alt="88 active tasks across six domains">
</p>

## 🚀 Quick Start

**1 — Install harbor**

```bash
uv tool install harbor
```

**2 — Get the tasks**

```bash
hf download AIMING-Lab-UNC/RSI-Exam --repo-type dataset --local-dir tasks/
```

**3 — Set task-side API keys, if the tasks you picked need them**

Four of the 35 public tasks call a model from inside the task — as a judge, or as the frozen base
model the agent optimises around. Copy [`.env.local.example`](.env.local.example) to `.env.local`
and fill in only what applies:

| Task | Key | What the model does there |
|---|---|---|
| `locomo_longterm_memory` | `MEMORY_LLM_API_KEY` | the frozen base of the memory system being optimised |
| `legal_matter_caseload_regulatory` | `APEX_LLM_API_KEY` | rubric judge over the submitted casework |
| `lean_formal_proof_workflow_design` | `LEAN_LLM_API_KEY` | the proof model the agent's workflow drives |
| `discoveryworld_agent_harness_low2` | `DISCOVERYWORLD_LLM_API_KEY` | the frozen model the harness under optimisation drives |

```bash
set -a; source .env.local; set +a
```

The other 31 tasks need none of this. Each key reaches only the task that declares it.

**4 — Set the run-wide variables**

```bash
export ARB_PROGRAM=$PWD/infra/prompts/autoresearch.md
export ARB_BUDGET_PY=$PWD/infra/prompts/budget.py
export ARB_AGENT_TIMEOUT_SEC=43200      # 12h, matching [agent] timeout_sec in the task
export ARB_OUTPUT_TOKEN_LIMIT=500000
```

**5 — Run it, then read it**

Credentials for the agent itself are per-harness; pick one from
[Harnesses & Models](#-harnesses--models) below and use its command as written.

```bash
harbor run -p tasks/<task> ...     # the harness command
harbor view jobs                   # point at jobs/, not at one job directory
```

## 🧩 What the Agent Is Given

Besides the task itself, two files are mounted into the agent's container.

**The instruction** — [`autoresearch.j2`](infra/prompts/autoresearch.j2). Keep improving an
inherited weak baseline: form a hypothesis, build it, measure it, log the version, repeat. And keep
in mind that the score you can see is only a proxy — the real grader is the sealed split you never
see. harbor renders it per task, together with the task's own `instruction.md`.

**The reminder** — [`budget.py`](infra/prompts/budget.py). Called by the task's own self-check, so
a budget line rides along with every measurement the agent takes. In the last 10% of the window it
turns into a wrap-up notice:

```
[budget] 648 / 720 min elapsed (90.0%) — your run window is nearly over. Wrap up soon and leave in
         /app/methods/main/ the version you want graded.
```

Both are mounted by [`mount.yaml`](infra/prompts/mount.yaml); pass the template through
`--ak prompt_template_path=` and the overlay through `--extra-docker-compose`.

## 🤖 Harnesses & Models

Eight harness+model combinations, with the exact command for each. **The commands differ in only
three places** — allowed hosts, the web-tool kill switch, and the effort flag — everything else is
identical.

| Harness | Model | Auth | Endpoint |
|---|---|---|---|
| codex | `gpt-5.6-sol`, `gpt-5.5` | `OPENAI_API_KEY` or `CODEX_AUTH_JSON_PATH` | openai.com |
| claude-code | `claude-opus-5` | `ANTHROPIC_API_KEY` or OAuth token | anthropic.com |
| claude-code | `glm-5.3[1m]` | `ANTHROPIC_AUTH_TOKEN` | api.z.ai |
| claude-code | `deepseek-v4-pro` | `ANTHROPIC_AUTH_TOKEN` | api.deepseek.com |
| qwen-coder | `qwen3.8-max` | `OPENAI_API_KEY` | maas.aliyuncs.com |
| antigravity-cli | `gemini/gemini-3.7-flash-high` | browser OAuth | googleapis.com |
| grok-build | `grok-4.6` | subscription OAuth | x.ai |

<details>
<summary><b>codex + gpt-5.6-sol</b></summary>

```bash
export OPENAI_API_KEY=sk-...      # or export CODEX_AUTH_JSON_PATH=$HOME/.codex/auth.json

harbor run -p tasks/<task> -a codex -m gpt-5.6-sol -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --ak web_search=disabled \
  --ak reasoning_effort=max \
  --allow-agent-host "*.openai.com"  --allow-agent-host openai.com \
  --allow-agent-host "*.chatgpt.com" --allow-agent-host chatgpt.com
```

</details>

<details>
<summary><b>claude-code + claude-opus-5</b></summary>

```bash
export ANTHROPIC_API_KEY=sk-ant-...

harbor run -p tasks/<task> -a claude-code -m claude-opus-5 -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --ak disallowed_tools="WebSearch,WebFetch" \
  --ak reasoning_effort=max \
  --ae ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5 \
  --ae ANTHROPIC_DEFAULT_SONNET_MODEL=claude-opus-5 \
  --ae ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-opus-5 \
  --ae CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5 \
  --allow-agent-host "*.anthropic.com" --allow-agent-host anthropic.com \
  --allow-agent-host "*.claude.ai"     --allow-agent-host claude.ai \
  --allow-agent-host "*.claude.com"    --allow-agent-host claude.com
```

</details>

<details>
<summary><b>claude-code + GLM-5.3 (z.ai)</b></summary>

```bash
export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic     # no trailing /v1
export ANTHROPIC_AUTH_TOKEN=<z.ai key>
unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN              # these two take precedence

harbor run -p tasks/<task> -a claude-code -m 'glm-5.3[1m]' -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --ak disallowed_tools="WebSearch,WebFetch" \
  --ak reasoning_effort=max \
  --allow-agent-host api.z.ai
```

With `ANTHROPIC_BASE_URL` set the adapter pins the four aliases itself, so no `--ae` here.

</details>

<details>
<summary><b>claude-code + DeepSeek-V4-Pro</b></summary>

```bash
unset OPENAI_BASE_URL OPENAI_API_KEY ANTHROPIC_API_KEY   # these three win otherwise
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic   # no trailing /v1
export ANTHROPIC_AUTH_TOKEN=<DeepSeek key>

harbor run -p tasks/<task> -a claude-code -m deepseek-v4-pro -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --ak disallowed_tools="WebSearch,WebFetch" \
  --ak reasoning_effort=max \
  --allow-agent-host api.deepseek.com
```

</details>

<details>
<summary><b>qwen-coder + qwen3.8-max</b></summary>

```bash
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY
export OPENAI_API_KEY=<Alibaba key, sk-sp-...>
export OPENAI_BASE_URL=https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
export ARB_QWEN_SETTINGS=$PWD/infra/prompts/qwen-settings.json

harbor run -p tasks/<task> -a qwen-coder -m qwen3.8-max -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --extra-docker-compose $PWD/infra/prompts/qwen-reasoning.yaml \
  --allow-agent-host token-plan.ap-southeast-1.maas.aliyuncs.com \
  --allow-agent-host "*.maas.aliyuncs.com"
```

</details>

<details>
<summary><b>antigravity-cli + gemini-3.7-flash-high</b></summary>

Sign-in is browser OAuth and needs a real terminal; 3.7 is only on the OAuth channel.

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash   # installs ~/.local/bin/agy
~/.local/bin/agy                     # Business account -> pick a GCP project
~/.local/bin/agy models              # confirm gemini-3.7-flash-high is listed

export ARB_AGY_SETTINGS=$HOME/.gemini/antigravity-cli/settings.json
export AGY_AUTH_JSON_PATH=$HOME/.gemini/antigravity-cli/antigravity-oauth-token

harbor run -p tasks/<task> -a antigravity-cli -m gemini/gemini-3.7-flash-high -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --ak output_format=stream-json \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --extra-docker-compose $PWD/infra/prompts/agy-provider.yaml \
  --allow-agent-host cloudcode-pa.googleapis.com \
  --allow-agent-host '*.rep.googleapis.com' \
  --allow-agent-host www.googleapis.com \
  --allow-agent-host oauth2.googleapis.com \
  --allow-agent-host accounts.google.com
```

⚠ **Apply the M3 patch first**, and after every harbor upgrade — without it any task longer than
five minutes is silently cut short and still graded.

```bash
bash infra/harbor/patch-antigravity-flags.sh
```

</details>

<details>
<summary><b>grok-build + grok-4.6</b></summary>

grok authenticates with a subscription login rather than a platform key. harbor's adapter only
knows `XAI_API_KEY` and builds a closed environment, so the login has to arrive as a file:
`grok-oauth.yaml` binds **just** `~/.grok/auth.json` into the container, read-write because the CLI
refreshes the token itself.

```bash
export XAI_API_KEY=unused-oauth-placeholder    # placeholder; the CLI uses auth.json

harbor run -p tasks/<task> -a grok-build -m grok-4.6 -y -n 1 \
  --ak prompt_template_path=$PWD/infra/prompts/autoresearch.j2 \
  --extra-docker-compose $PWD/infra/prompts/mount.yaml \
  --extra-docker-compose $PWD/infra/prompts/grok-oauth.yaml \
  --ak reasoning_effort=xhigh \
  --allow-agent-host api.x.ai \
  --allow-agent-host cli-chat-proxy.grok.com \
  --allow-agent-host auth.x.ai
```

</details>

Every task runs `no-network` in both the agent and the verifier phase — the `--allow-agent-host`
lines above are the only opening, and they are supplied at run time so no endpoint is ever baked
into a task. Full specification: [`docs/network-policy.md`](docs/network-policy.md).

## 📊 Running a Batch

Point `-p` at a directory that is not itself a task and harbor enumerates it as a dataset:

```bash
harbor run -p tasks -a codex -m gpt-5.6-sol -n 8 ...        # everything under tasks/
harbor run -p tasks -i gate_sizing -i "mbff*" -n 3 ...      # just these, glob allowed
harbor run -p tasks -x "bigann*" -n 8 ...                   # everything except
```

**`-n` is a concurrency ceiling, not a batch size.** harbor schedules with a rolling semaphore: more
tasks than `-n` is fine, one finishes and the next starts. There is no need to split by hand.

**`-k` repeats each task.** `-k 3` gives three fully independent trials per task — separate
containers, separate budgets, separate `reward.json`, nothing averaged for you. These tasks are
stochastic, so a single trial is a sample, not a measurement; use `-k` when a number has to be
defensible. Total work is `tasks × k`, still bounded by `-n`.

## 📁 Reading Results

```
jobs/<timestamp>/<task>__<id>/
  agent/<harness>.txt          full trajectory — claude-code.txt · codex.txt ·
                               qwen-code.txt · grok-build.txt
  agent/trajectory.json        normalized ATIF trajectory
  artifacts/app/methods/       what the agent submitted, including versions/
  verifier/reward.json         the hidden-set score, plus the task's own raw metric
  result.json  trial.log  config.json
```

```bash
harbor view jobs                       # web UI; point at jobs/, not at one job directory
harbor upload jobs/<timestamp>         # share a run
```

The web UI reads one level down, so pointing it at a single job directory gives a blank page.
Selecting several trajectories compares their scores side by side.

## 📈 Example Trajectory

A GPT-5.6-sol run on `discoveryworld_agent_harness_low2`, reconstructed from `experiment_log.md`
and the saved snapshots: over 10.5 hours the visible suite mean climbs from 0.10 to 0.63.

<p align="center">
  <img src="assets/trajectory-example.png" width="880" alt="Best-so-far visible suite mean against elapsed time for one 10.5-hour rollout, rising from 0.10 to 0.63 in a few large steps">
</p>

On the hidden set, the same metric moves from the baseline's 0.13 to **0.26**: it is the harder
split, and a gain measured on the visible one does not necessarily transfer.

## 🏆 Leaderboard

Mean hidden-set score over all 88 tasks.

<p align="center">
  <img src="assets/leaderboard.png" width="880" alt="Mean hidden-set score over all 88 tasks, from Opus 5 at 0.464 down to Gemini 3.7 Flash at 0.309">
</p>

Against what it costs to get there:

<p align="center">
  <img src="assets/cost-score.png" width="880" alt="Mean hidden-set score versus average spend per task">
</p>

Per-split boards and per-task trajectories for all nine models are at
[rsi-exam.ai](https://rsi-exam.ai).

## 🔗 Related

- **Website and leaderboard** — [rsi-exam.ai](https://rsi-exam.ai)
- **Public tasks** — [🤗 AIMING-Lab-UNC/RSI-Exam](https://huggingface.co/datasets/AIMING-Lab-UNC/RSI-Exam)
- **Task pages** — [rsi-exam.ai/tasks.html](https://rsi-exam.ai/tasks.html), every task with its
  metric, its anchors, and the trajectories of nine models
- **harbor** — [harborframework.com](https://www.harborframework.com/)

## 📄 License

MIT. See [LICENSE](LICENSE).

## 📮 Contact

For questions, feedback, evaluation on the full 88-task suite, or contributions, join us on
[Discord](https://discord.gg/FBzhepyE) or write to
[contact@rsi-exam.ai](mailto:contact@rsi-exam.ai).
