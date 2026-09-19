#!/usr/bin/env python3
"""Local validation for the decision-isolation runtime (no Docker needed).

Runs four checks on short streams:

  1. PARITY      — legacy in-process runner vs decision-isolated runner must
                   produce bit-identical summary metrics for the starter and
                   the strong reference (c4).
  2. STRIPPING   — inside the decision server, v_net.lifetime and
                   v_net.arrival_time are None (physically stripped), while the
                   substrate snapshot carries live resource state.
  3. BUDGET      — a solver that sleeps past the per-request alarm gets every
                   request counted as rejected; the stream completes; no
                   restarts (state-preserving timeout path).
  4. CRASH       — a solver that raises fails the stream loudly
                   (ChildSolverError), i.e. a legitimate 0, not a hang.

    .venv/bin/python validation/parity_local.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "environment"))
import virne_task_lib as vtl  # noqa: E402

# short streams for speed
vtl.NUM_V_NETS = 120

STARTER = ROOT / "environment" / "methods" / "main" / "solver.py"
C4 = ROOT / "tests" / "solution" / "solver.py"
SERVER = ROOT / "environment" / "decision_server.py"

SEED = 0


def prepare_data(data_root: Path) -> None:
    vtl.NUM_V_NETS_SAVE = vtl.NUM_V_NETS
    vtl.materialize_split("visible", str(data_root))


def probe_solver(code: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="probe_"))
    (d / "solver.py").write_text(textwrap.dedent(code))
    return d / "solver.py"


def run_legacy(solver: Path, data_root: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="leg_") as tmp:
        return vtl.run_stream(str(solver), SEED, str(data_root), tmp, "leg")


def run_isolated(solver: Path, data_root: Path, cfg) -> dict:
    client = vtl.DecisionClient(str(solver), server_script=str(SERVER), config=cfg)
    try:
        with tempfile.TemporaryDirectory(prefix="iso_") as tmp:
            return vtl.run_stream_isolated(client, SEED, str(data_root), tmp, "iso")
    finally:
        client.close()


def check(name: str, cond: bool, extra: str = "") -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    return cond


def main() -> int:
    ok = True
    data_root = Path(tempfile.mkdtemp(prefix="nfv_data_"))
    prepare_data(data_root)
    print(f"data: {data_root} (NUM_V_NETS={vtl.NUM_V_NETS}, seed {SEED})")

    import os
    cwd = os.getcwd()
    os.chdir(data_root)
    try:
        cfg = vtl.compose_config(SEED)
    finally:
        os.chdir(cwd)

    # ---------------------------------------------------------------- 1. PARITY
    print("\n[1] parity: legacy in-process vs decision-isolated")
    for label, solver in (("starter", STARTER), ("strong-ref (c4)", C4)):
        t0 = time.time()
        a = run_legacy(solver, data_root)
        b = run_isolated(solver, data_root, cfg)
        if label == "strong-ref (c4)":
            same = (a["mean_score"] == b["mean_score"]
                    and a["acceptance_rate"] == b["acceptance_rate"]
                    and a["long_term_r2c_ratio"] == b["long_term_r2c_ratio"])
            ok &= check(f"{label}: identical accounting (required)",
                        same,
                        f"(legacy {a['mean_score']:.4f}/ac{a['acceptance_rate']:.4f} vs "
                        f"isolated {b['mean_score']:.4f}/ac{b['acceptance_rate']:.4f}, "
                        f"{time.time()-t0:.0f}s)")
        else:
            # Verdict semantics intentionally differ for solvers that leave
            # failed-attempt residue (legacy poisoned accepted solutions with
            # intermediate bookkeeping; the isolated runtime re-verdicts via
            # trusted feasibility). Recorded, not asserted.
            print(f"  [INFO] {label}: legacy {a['mean_score']:.4f}/"
                  f"ac{a['acceptance_rate']:.4f} vs isolated "
                  f"{b['mean_score']:.4f}/ac{b['acceptance_rate']:.4f} "
                  f"(verdict-semantics change, see README)")
    # isolated runtime must be self-consistent (deterministic)
    b1 = run_isolated(STARTER, data_root, cfg)
    b2 = run_isolated(STARTER, data_root, cfg)
    ok &= check("isolated starter: run-to-run determinism",
                b1["mean_score"] == b2["mean_score"]
                and b1["acceptance_rate"] == b2["acceptance_rate"])

    # ------------------------------------------------------------- 2. STRIPPING
    print("\n[2] observability stripping inside the decision server")
    obs_path = Path(tempfile.mkdtemp(prefix="obs_")) / "observed.json"
    probe = probe_solver(f"""
        import json
        from virne.core import Solution
        from virne.solver.base_solver import Solver

        class Submission(Solver):
            def solve(self, instance):
                v_net, p_net = instance["v_net"], instance["p_net"]
                obs = {{
                    "lifetime": getattr(v_net, "lifetime", "MISSING"),
                    "arrival_time": getattr(v_net, "arrival_time", "MISSING"),
                    "id": getattr(v_net, "id", "MISSING"),
                    "node_attr_sample": dict(p_net.nodes[list(p_net.nodes)[0]]),
                    "num_nodes": p_net.num_nodes,
                }}
                with open(r"{obs_path}", "a") as f:
                    f.write(json.dumps(obs) + "\\n")
                solution = Solution.from_v_net(v_net)
                solution.update({{"place_result": False, "result": False}})
                return solution
    """)
    m = run_isolated(probe, data_root, cfg)
    rows = [json.loads(x) for x in obs_path.read_text().splitlines()]
    ok &= check("lifetime is None in child",
                all(r["lifetime"] is None for r in rows))
    ok &= check("arrival_time is None in child",
                all(r["arrival_time"] is None for r in rows))
    ok &= check("p_net snapshot carries live resources",
                all(isinstance(r["node_attr_sample"], dict) and
                    r["node_attr_sample"] for r in rows),
                f"sample={rows[0]['node_attr_sample']}")
    ok &= check("probe stream scored as all-rejected",
                m["acceptance_rate"] == 0.0)

    # ---------------------------------------------------------------- 3. BUDGET
    print("\n[3] per-request budget (child-side alarm, state-preserving)")
    sleeper = probe_solver("""
        import time
        from virne.core import Solution
        from virne.solver.base_solver import Solver

        class Submission(Solver):
            def solve(self, instance):
                time.sleep(30.0)          # far past the 2.7 s child alarm
                raise AssertionError("unreachable")
    """)
    t0 = time.time()
    m = run_isolated(sleeper, data_root, cfg)
    elapsed = time.time() - t0
    ok &= check("every request rejected on timeout",
                m["acceptance_rate"] == 0.0, f"({m['request_timeouts']} timeouts)")
    ok &= check("no server restarts (state preserved)",
                m["decision_server_restarts"] == 0)
    ok &= check("wall-clock sane for 120 rejected requests",
                elapsed < 120 * 3.0, f"({elapsed:.0f}s)")

    # ----------------------------------------------------------------- 4. CRASH
    print("\n[4] crashing submission fails the stream loudly")
    crasher = probe_solver("""
        from virne.solver.base_solver import Solver

        class Submission(Solver):
            def solve(self, instance):
                raise RuntimeError("boom")
    """)
    try:
        run_isolated(crasher, data_root, cfg)
        ok &= check("ChildSolverError raised", False)
    except vtl.ChildSolverError as exc:
        ok &= check("ChildSolverError raised", True, f"({str(exc)[:40]})")

    # ------------------------------------------------------- 5. ADVERSARIAL DECISION
    print("\n[5] infeasible claimed embedding is rejected by trusted replay")
    cheater = probe_solver("""
        from collections import OrderedDict
        from virne.core import Solution
        from virne.solver.base_solver import Solver

        class Submission(Solver):
            def solve(self, instance):
                v_net, p_net = instance["v_net"], instance["p_net"]
                sol = Solution.from_v_net(v_net)
                # claim every virtual node onto the physical node with the
                # LEAST cpu: within-request sequential usage guarantees
                # infeasibility for any multi-node request
                p_min = min(p_net.nodes, key=lambda n: p_net.nodes[n]["cpu"])
                slots, info = OrderedDict(), OrderedDict()
                for v in v_net.nodes:
                    slots[v] = p_min
                    info[(v, p_min)] = {"cpu": v_net.nodes[v]["cpu"]}
                sol.update({"node_slots": slots, "node_slots_info": info,
                            "link_paths": OrderedDict(),
                            "link_paths_info": OrderedDict(), "result": True})
                return sol
    """)
    m = run_isolated(cheater, data_root, cfg)
    ok &= check("every infeasible claim rejected",
                m["acceptance_rate"] == 0.0,
                f"(ac={m['acceptance_rate']:.3f})")
    ok &= check("no server restarts during adversarial run",
                m["decision_server_restarts"] == 0)

    shutil.rmtree(data_root, ignore_errors=True)
    print("\nRESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
