# Online NFV Resource Allocation Research

## Goal

You inherit a weak Python solver that embeds arriving virtual networks onto a shared
substrate network. Improve it into the best deterministic heuristic you can, and
deliver it at `/app/methods/main/solver.py`. Your submitted solver is re-run from
scratch on sealed request streams from the same generators; the objective is
**long-term time-averaged revenue**, higher is better, normalized against measured
reference points on each stream.

Every embedding decision changes what can be accepted later: a request accepted
today consumes capacity tomorrow's requests needed, and a badly placed one
fragments the substrate and starves everything after it. The job is not to squeeze
any single embedding — it is to keep the substrate earning for the whole horizon.

## Workspace

- `/app/methods/main/solver.py`: the starting solver — virtual nodes in insertion
  order, first feasible substrate node, one attempt, no awareness of load or
  locality. It defines the zero point and shows the plumbing; it is not the
  intended shape of your answer. Everything you keep under `/app/methods/` travels
  with your submission.
- `/app/data/` (see `manifest.json`): three visible request streams — 1,000
  arrivals each, Poisson rate 0.12, exponential lifetimes, sizes 2–10 nodes — each
  on its own 100-node substrate topology.
- `/app/selfcheck.py`: free self-check that runs your current solver on every
  visible stream through the SAME decision-isolation runtime and accounting
  the sealed grader uses (~20 s to ~3 min per stream; a seed argument checks
  just that stream).
- The `virne` package (networkx, numpy, scipy, ortools included): drive the
  simulation through `self.controller` — feasibility filter
  (`find_candidate_nodes`), incremental placement+routing (`place_and_route`),
  undo (`undo_place_and_route`) — or compute embeddings entirely yourself and
  report them through a `Solution`. No reference solver ships with the image:
  every original solver, learning-based and heuristic alike, was removed, so the
  method you submit is entirely yours. The simulator core, its control primitives,
  and `virne.solver.base_solver.Solver` are what there is to read.

## Reference baseline

The shipped first-fit starter anchors the low end of the normalized scale. A
classical node-ranking mapping and a stronger hand-tuned heuristic sit between it
and the ceiling; none of them ship with the image, and the literature state of
the art is yours to rebuild. The scale's ceiling (1.00) is the stream's **accept-all oracle** — every
request embedded at arrival and served its full lifetime — computed exactly from
the stream itself; no capacity-respecting solver can reach it. The normalized
score is a monotonic function of sealed performance; optimize raw revenue and
cross-stream generalization, not the normalization.

## Research loop

1. Form a hypothesis about what limits long-run revenue (fragmentation, myopic
   ranking, routing waste, rejection policy).
2. Implement it in `/app/methods/main/solver.py` (helper modules next to it are
   fine), and record the attempt in `/app/methods/experiment_log.md` — what
   changed, the visible scores it measured, kept or reverted. Save evaluated
   snapshots under `/app/methods/versions/vN/`.
3. Self-check on the visible streams with `/app/selfcheck.py`.
4. Call `rsi-submit` when a candidate looks better. Your workspace is snapshotted
   and the sealed grader re-runs your solver on the hidden streams, returning the
   aggregate normalized score plus bounded diagnostics (acceptance ratio,
   revenue-to-cost) per submission.
5. Read the feedback, keep or revert, and iterate. Avoid submitting noise: each
   submission costs a snapshot round, and the best **valid** submission is the one
   that counts — a trailing weaker submission cannot hurt you, but a broken one
   wastes a round.

## What you may change

- Everything under `/app/methods/` — including deleting the starter entirely and
  designing your method from scratch.
- Any classical technique: greedy construction, ranking rules, local search,
  lookahead, retry/backtracking, exact or meta-heuristic methods — as long as they
  fit the time budget and the constraints below.

## What stays fixed

- `class Submission(Solver)` with `solve(self, instance) -> Solution`, where
  `instance = {'v_net': ..., 'p_net': ...}`. Return `solution['result'] = True`
  for an accepted embedding, or `solution.update({'result': False,
  'place_result': False})` for a rejection with any partial placement rolled
  back. An invalid or crashing submission scores zero on that stream.
- **An algorithm, not precomputed answers**: solvers must not key on stream seeds
  or names.
- **Heuristics only**: no neural networks, no learned models, no training, no
  pretrained weights.
- **Arrival-observable information only**: this request's demands and topology,
  and the substrate's *current* remaining capacity. This is enforced by
  construction, not by trust: at runtime your solver executes in a separate
  decision server that receives only the current request — `v_net.lifetime`
  and `v_net.arrival_time` are `None` in every instance you receive, the
  stream files are unreachable from that process, and no future event ever
  crosses the boundary. Solvers must not attempt to read stream data files or
  any source of future arrivals.
- **Deterministic for a given stream**: no wall-clock dependence, no unseeded
  randomness — and your solver must never read the clock. Each request gets a
  hard 3-second budget **enforced by the harness** (SIGALRM watchdog): an overrun
  is rolled back and counted as rejected, and the stream continues.
- Do not modify `/app/selfcheck.py`, the data under `/app/data/`, or anything
  outside `/app/methods/`. Nothing outside `methods/main/` is used at grading
  time.

## Evaluation and feedback

Your solver runs in an isolated decision server; the judge's trusted process
owns the simulation, the accounting, and the score. Every accepted decision you
return is re-validated structurally (exact coverage, distinct existing nodes,
continuous existing-edge paths) and resource-wise (each assignment fits the
substrate's current remaining capacity) by trusted code before it is deployed;
a forged or infeasible decision is rejected for that request — it can never
increase the score. The per-request 3-second budget is enforced by the harness
in both processes (your solver state survives a timeout; a hard hang may
restart the decision server, losing in-memory state). `self.recorder` and
`self.counter` are inert stand-ins on your side of the fence — `self.controller`
is the sanctioned interface. The raw metric is each stream's long-term
time-averaged revenue, scored per stream against its own measured reference
points and averaged. Feedback per submission is limited to the aggregate
normalized score and bounded diagnostics; the hidden streams are disjoint from
the visible ones but use the identical generators, load, and accounting.

## Submission checklist

Before each `rsi-submit`:

- [ ] `/app/methods/main/solver.py` defines `class Submission(Solver)` and runs
      `selfcheck.py` without crashing on all three visible streams.
- [ ] The solver is deterministic, reads no clock, and uses no future stream
      information.
- [ ] `/app/methods/experiment_log.md` records what changed since the last round.
