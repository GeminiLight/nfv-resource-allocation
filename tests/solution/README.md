# solution/ — author-side strong reference (0.60 tier), published for audit

`solver.py` is **rsi-c4**: the strong heuristic anchor (normalizes to 0.60),
standalone — it vendors its base class in `rsi_search.py`, no author checkout
required. NEVER ships in the agent image (the build asserts the solver
registry is empty); it lives here and in the verifier image's oracle-CI slot
only.

## Measured anchors (decision-isolation runtime, full 1000-request streams,
## 2026-09-19 — see ../../validation/anchors_remeasured.json)

- heldout (s42/s137/s2024): 9469.0 / 9546.1 / 9574.0  (ac 0.805/0.805/0.832)
- visible (s0/s1/s2):       10893.7 / 10723.3 / 10563.0

Legacy in-process-runtime numbers for the same heldout streams (documented
reference only — that runtime flipped 69/1000 of c4's accepted solutions to
rejected via intermediate-attempt violation bookkeeping): 9299 / 9815 / 9701.

Historical lineage: c4 = second search round at the final rate-0.12 regime
(33 configs over 4 rounds; the first champion v17 was tuned at the old
rate-0.08 regime — v17 numbers on the then-current streams were hidden
8502/8881/8953, visible 9928/9822/9531 — and is 7.7% under c4 at 0.12).

Reference points on the same heldout streams (rate 0.12, AS routing):
published heuristic SOTA pl_rank 8233/8360/8294 (normalizes ≈ 0.49); trained
ppo_dual_gat+ (out of scope) 9666/9922/10014 — the heuristic frontier is
dense at this load.
