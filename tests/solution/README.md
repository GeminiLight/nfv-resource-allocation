# solution/ — author-side only, excluded from any public release

`solver.py` exposes the strong reference (0.60 tier anchor) as a `Submission` shim
around `virne.solver.heuristic.rsi_search.RsiV17` (the search module lives in the
author's virne checkout; for the final verifier image either vendor the ~200-line
module here or re-implement standalone — then re-measure anchors in that image).

Measured through the task's own runner, 2026-08-31/09-01:
- hidden  : 8502 / 8881 / 8953  (mean 8778)
- visible : 9928 / 9822 / 9531  (mean 9760)
Weak tier (nrm_rank): hidden 5508 / 5851 / 5719 (mean 5693).
Starter template  : hidden 1312 / 1917 / 2094 (mean 1774).
