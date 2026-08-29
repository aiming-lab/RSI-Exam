# GPU Tasks on the Docker Backend (with no network)

For GPU tasks running on a local docker backend. Everything here is a mistake already made once;
follow it in order.

## 1. Do not put `gpus` in `task.toml`

harbor's docker backend **does not support the field**, and exits before building the image:

```
Task requires 1 GPU(s) but docker environment does not support GPU allocation.
```

`gpus` defaults to false in the docker backend's capability table
(`harbor/environments/capabilities.py`), and `BaseEnvironment.__init__` calls
`_validate_gpu_support()`, which raises (`harbor/environments/base.py:217`).

So **omit** `gpus` in both `[environment]` and `[verifier.environment]`. The card does not enter
through there.

## 2. The card comes in through a compose overlay — in both containers

`environment/docker-compose.yaml` (agent container) and `tests/docker-compose.yaml` (grading
container) each get the same block:

```yaml
services:
  main:
    environment:
      NVIDIA_VISIBLE_DEVICES: "$HARBOR_GPU_DEVICE"
      NVIDIA_DRIVER_CAPABILITIES: "compute,utility"
      CUDA_VISIBLE_DEVICES: "0"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["$HARBOR_GPU_DEVICE"]
              capabilities: [gpu]
```

⚠ **Both, not just one.** With only the grading side, the agent container falls back to the
image's `ENV NVIDIA_VISIBLE_DEVICES=all` and **sees every card on the host** — including ones other
people are using. The agent then self-checks on one card while grading measures another, the
numbers do not line up, and four hours are wasted.

⚠ Inside the container the card is always **device 0**: only one is passed in, and numbering
restarts. Grading code should use `torch.cuda.get_device_name(0)`.

## 3. Pass the number as a variable, never hard-coded

```yaml
device_ids: ["${HARBOR_GPU_DEVICE:?set HARBOR_GPU_DEVICE}"]
```

`${VAR:?message}` is compose syntax: unset means abort with that message. A hard-coded number is
wrong on the next machine, and wrong silently — it still runs, just on the wrong card.

```bash
export HARBOR_GPU_DEVICE=1        # the index from nvidia-smi -L on the host
```

⚠ **Identify cards by UUID, not index.** Check `nvidia-smi -L` and use the card the anchors were
measured on. Two cards of the same model measurably differ.

## 4. Time-based grading also needs a pinned CPU

`cpus = N` in `task.toml` is only a CFS quota ("N cores' worth of time"), **not exclusive cores**.
A task judged on wall time must pin a cpuset as well, or the numbers move with whatever the
neighbours are doing:

```yaml
services:
  main:
    cpuset: "${HARBOR_CPUSET:?set HARBOR_CPUSET}"
```

⚠ If the grading code asserts a specific core (`sched_getaffinity(0) == {8}`), `HARBOR_CPUSET` can
only be that core — changing it means changing the code too.

## 5. Network

The three-phase policy goes in `task.toml` as usual (see [`network-policy.md`](network-policy.md)):

```toml
[agent]
network_mode = "no-network"     # the model endpoint is added at run time

[environment]
network_mode = "public"         # for installing codex / claude-code; no agent code is running yet

[verifier]
environment_mode = "separate"
[verifier.environment]
network_mode = "no-network"
```

🚨 **An overlay must never contain `networks:` or `network_mode:`.** harbor's
`_egress_controlled_service_names()` **skips** any service that declares either key — the task says
sealed, the container is wide open, and nothing reports an error. The two GPU overlays above touch
only `environment` / `deploy` / `cpuset`, which is safe.

⚠ The build phase (`RUN` in a Dockerfile) is not covered by any of the three and goes over docker's
default bridge — dependencies and data are baked in there, which is the legitimate, and only, time
to download.

## 6. Check before running

```bash
# is the card there, is the index right
nvidia-smi -L

# does task.toml pass harbor's own validation (gpus should be None)
python -c "import tomllib; from harbor.models.task.config import TaskConfig; \
  print(TaskConfig.model_validate(tomllib.load(open('<task>/task.toml','rb'))).environment)"

# do the compose variables interpolate (expect cpuset / device_ids / NVIDIA_VISIBLE_DEVICES)
printf 'services:\n  main:\n    image: busybox\n' > /tmp/base.yaml
docker compose -f /tmp/base.yaml -f <task>/environment/docker-compose.yaml config
```

Then run an oracle smoke test before putting an agent on it: the starting solution should score a
reward of 0, and per-instance timings should sit close to the frozen baseline. If they do not, the
environment has not been reproduced — and finding that out here is far cheaper than after four
hours.
