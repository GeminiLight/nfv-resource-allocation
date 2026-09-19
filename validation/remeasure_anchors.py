#!/usr/bin/env python3
"""Re-measure the scoring anchors through the DECISION-ISOLATION runtime.

Anchors must be measured through the same runner that grades submissions. The
isolated runtime's acceptance verdict is re-computed by trusted feasibility
replay (no intermediate-attempt bookkeeping), so the starter tier shifts
slightly upward vs the legacy in-process measurements; the strong reference
(c4) is bit-identical to legacy by construction (validated in parity_local).

Measures, on FULL 1000-request streams:
  - starter  (scoring anchor B, normalized 0.00)
  - c4       (scoring anchor S, normalized 0.60)
on visible seeds 0/1/2 and heldout seeds 42/137/2024, and writes
validation/anchors_remeasured.json for updating tests/anchors.json.

    .venv/bin/python validation/remeasure_anchors.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "environment"))
import virne_task_lib as vtl  # noqa: E402

STARTER = ROOT / "environment" / "methods" / "main" / "solver.py"
C4 = ROOT / "tests" / "solution" / "solver.py"
SERVER = ROOT / "environment" / "decision_server.py"

VISIBLE = [0, 1, 2]
HELDOUT = [42, 137, 2024]


def measure(solver: Path, seeds: list, data_root: Path, cfg) -> dict:
    out = {}
    client = vtl.DecisionClient(str(solver), server_script=str(SERVER), config=cfg)
    try:
        for seed in seeds:
            t0 = time.time()
            with tempfile.TemporaryDirectory(prefix=f"am_s{seed}_") as tmp:
                m = vtl.run_stream_isolated(client, seed, str(data_root), tmp,
                                            f"am-s{seed}")
            out[f"s{seed}"] = {
                "mean_score": m["mean_score"],
                "acceptance_rate": m["acceptance_rate"],
                "avg_r2c_ratio": m["avg_r2c_ratio"],
                "wall_sec": round(time.time() - t0, 1),
                "request_timeouts": m["request_timeouts"],
                "restarts": m["decision_server_restarts"],
            }
            print(f"  s{seed}: revenue={m['mean_score']:.1f} "
                  f"ac={m['acceptance_rate']:.3f} ({out[f's{seed}']['wall_sec']}s)",
                  flush=True)
    finally:
        client.close()
    return out


def main() -> int:
    assert vtl.NUM_V_NETS == 1000, "anchors need the full frozen regime"
    data_root = Path(tempfile.mkdtemp(prefix="anchors_"))
    print(f"materializing visible + heldout splits at {data_root} ...")
    vtl.materialize_split("visible", str(data_root))
    vtl.materialize_split("heldout", str(data_root))

    import os
    cwd = os.getcwd()
    os.chdir(data_root)
    try:
        cfg = vtl.compose_config(0)
    finally:
        os.chdir(cwd)

    result = {"runtime": "decision-isolated", "num_v_nets": vtl.NUM_V_NETS,
              "rate": vtl.ARRIVAL_RATE, "measured_at": time.strftime("%Y-%m-%d")}
    for label, solver in (("starter", STARTER), ("c4", C4)):
        print(f"\n== {label} ==")
        result[label] = {"visible": measure(solver, VISIBLE, data_root, cfg),
                         "heldout": measure(solver, HELDOUT, data_root, cfg)}

    out_path = ROOT / "validation" / "anchors_remeasured.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {out_path}")

    def tier(sol, split, seeds):
        return [round(result[sol][split][f"s{s}"]["mean_score"], 1) for s in seeds]
    print("starter heldout :", tier("starter", "heldout", HELDOUT))
    print("c4      heldout :", tier("c4", "heldout", HELDOUT))
    print("starter visible :", tier("starter", "visible", VISIBLE))
    print("c4      visible :", tier("c4", "visible", VISIBLE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
