# nfv-resource-allocation — task package & audit evidence

OpenRSI-Index task proposal evidence for **`rsi/nfv-resource-allocation`**
(Discussion: OpenRSI-Foundation/OpenRSI-Index#85). This repository contains the
complete task overlay the proposal refers to, in the exact layout the private
task repository is built from. Everything a reviewer needs to audit baseline
provenance, grader integrity, and evaluation semantics is public here; runtime
separation (Judge-only image, no-network agent, per-request snapshots) — not
obscurity — is what protects the sealed streams during runs.

## Layout

```
task.toml                      # OpenRSI schema 1.4 manifest
instruction.md                 # agent-facing task statement (rsi-submit loop)
environment/                   # AGENT image: visible streams + decision server
  Dockerfile                   #   build: vendored heuristics-only virne + visible split
  virne_task_lib.py            #   config compose, data materialize, runners (incl. isolation layer)
  decision_server.py           #   UNTRUSTED side: per-request snapshots -> JSON decisions
  prepare_data.py              #   --split visible|heldout, same generator both sides
  selfcheck.py                 #   free self-check through the SAME isolated runtime
  methods/main/solver.py       #   first-fit starter (the inherited zero point)
tests/                         # VERIFIER image: sealed streams + trusted grader
  Dockerfile                   #   build: heldout split lands here, ROOT-ONLY perms
  grade.py                     #   TRUSTED grader: runs streams in-process, owns scoring
  decision_server.py -> ../environment/decision_server.py (staged by build.sh)
  score.py                     #   sanity gates (defense in depth)
  anchors.json                 #   sealed anchor table (also published here for audit)
  test.sh                      #   fail-closed wrapper, deletes seeded reward files
  solution/                    #   author-side strong reference (rsi-c4, 0.60 tier)
virne-src/                     # vendored heuristics-only build of GeminiLight/virne
                                # @ 4fd97f2b (learning stack stripped; no torch)
validation/
  parity_local.py              # 14-check local validation suite (no Docker needed)
  remeasure_anchors.py         # anchor measurement through the isolated runtime
  anchors_remeasured.json      # measured anchor tables (visible + heldout)
build.sh                       # assembles both Docker build contexts and builds
```

## The decision-isolation runtime (what the integrity review asked for)

The two hard findings of the first rubric review were (1) arrival-observability
was a declared rule with no enforcement, and (2) the submission shared a process
with the accounting objects that produce the score. Both are resolved by
construction:

1. **The untrusted process cannot see the future.** The submission executes in
   `decision_server.py` (uid 65534). Per request it receives a snapshot:
   the current `v_net` with `lifetime`/`arrival_time` **physically set to
   None**, and the current `p_net` resource state. Held-out stream files are
   `root:root go-rwx` in the verifier image and are never opened by the
   decision server. There is nothing to police because the information is not
   there — verified by `validation/parity_local.py` check [2].
2. **The untrusted process cannot touch the score.** The simulation, constraint
   checking, and metric accounting run in the trusted grader process (virne's
   own `OnlineSystem`/`Recorder`/`Counter`). The decision server holds no
   accounting objects and no reward path. Every returned decision is
   re-validated by trusted code (structural contract + per-assignment resource
   feasibility, mirroring the controller's own per-step semantics) before
   deployment; a forged or infeasible decision is rejected for that request and
   can never increase the score — verified by check [5] (adversarial
   oversubscription attempt scores zero).
3. **Budgets are enforced on both sides.** Per-request SIGALRM in the decision
   server (2.7 s, state-preserving) with the vendored `OnlineSystem` watchdog
   (3.0 s) as parent-side backstop; a hung server is respawned before the next
   request. Verified by check [3]; crashes fail the stream loudly (check [4]).

## Verdict semantics note (documented deviation from the legacy runtime)

The legacy in-process runner accumulated constraint-violation bookkeeping from
abandoned intermediate attempts and used it to flip otherwise-feasible accepted
solutions to rejected (69/1000 requests for the strong reference on stream
s137). The isolated runtime instead accepts any structurally valid,
resource-feasible final decision. This is a deliberate cleanup: anchors were
re-measured through the isolated runtime accordingly (`anchors.json`,
`validation/anchors_remeasured.json`): starter (0.00 tier) 4065.9/4303.5/4591.6,
rsi-c4 (0.60 tier) 9469.0/9546.1/9574.0 on the held-out streams; the
accept-all oracle ceiling is computed offline from the streams and is
unchanged. Transport fidelity is proven bit-identical for the strong reference
in the no-intermediate-failure regime (validation check [1]) plus targeted
single-variable probes (v_net stripping, p_net pickle round-trip, fresh
controller — all state-neutral).

## Reproduce locally (no Docker)

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python ./virne-src
.venv/bin/python validation/parity_local.py        # 14 checks, ~15 min
.venv/bin/python validation/remeasure_anchors.py   # full-stream anchors, ~30 min
./build.sh                                          # both Docker images (needs daemon)
```

## Sealed-material policy

Following this repository's own convention (public task repos ship tests and
author-side solutions; the runtime — not the repo — is sealed), the anchor
table and the strong reference are published here for auditability. During a
run, the agent image contains none of it: no solver beyond the starter ships
(the build asserts the solver registry is empty), and held-out streams exist
only in the verifier image.

## Author

Tianfu Wang <tianfuwang.cs@gmail.com> (GitHub: GeminiLight) — author of the
pinned upstream [GeminiLight/virne](https://github.com/GeminiLight/virne)
(ICLR 2026 benchmark paper, arXiv:2507.19234).
