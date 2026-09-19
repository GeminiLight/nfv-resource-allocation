"""TRUSTED grader for nfv_resource_allocation (decision-isolation runtime).

Runs the sealed streams through virne's own OnlineSystem IN THIS PROCESS (as
root): the simulation, constraint checking and metric accounting are trusted
library code. The submission is never imported here — it runs inside a
privilege-dropped decision server (uid 65534) that receives only per-request
snapshots (current v_net with lifetime/arrival_time stripped to None; current
p_net resource state) and answers with JSON decisions that this grader
re-validates through virne's own solution contract before deployment.

Isolation properties (mechanically enforced, not declared):
  * future information: held-out stream files are root-only and never enter
    the decision server; each snapshot contains only the CURRENT request;
    lifetime/arrival_time are physically None in the child;
  * accounting: the score is produced by virne's Recorder/Counter in THIS
    process; the child holds no accounting objects and no reward path;
  * budget: per-request SIGALRM in the child (state-preserving) with the
    vendored OnlineSystem watchdog as parent-side backstop; a hung child is
    respawned before the next request (in-memory solver state lost, logged).

Reward band (higher-is-better). Two measured anchors + an oracle upper bound:
starter B -> 0.0, strong reference S -> 0.60, oracle U -> 1.0, piecewise
log-linear in u(m) = log(m + shift). See anchors.json for provenance.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_here = Path(__file__).parent
sys.path.insert(0, str(_here.parent / "environment"))   # decision_server.py + lib
import score as scorer  # noqa: E402  (sanity gate)
from virne_task_lib import (  # noqa: E402
    DecisionClient, compose_config, run_stream_isolated,
)

# --- HARD-CODED constants (never os.environ.get — the host must not be able to
#     weaken the grader by setting a container env var) ------------------------
ANCHOR_FILE = Path("/tests/anchors.json")     # root-owned, 0400
SERVER = Path("/tests/decision_server.py")
SUBMISSION_DIR = Path("/app/methods/main")    # Work snapshot mount
DATA_ROOT = Path("/tests/data")               # sealed streams, root-only
REWARD_DIR = Path("/logs/verifier")
SOLVER_UID = 65534                            # nobody
SOLVER_GID = 65534
TIME_BUDGET_SEC = 3600.0                      # per stream
GRACE_SEC = 30.0
GRADER_FAIL = "grader failed: "


class _StreamTimeout(Exception):
    pass


def _load_anchors() -> dict:
    a = json.loads(ANCHOR_FILE.read_text())
    if a.get("direction") != "higher":
        raise ValueError("this grader implements direction=higher")
    for case, v in a["cases"].items():
        if not (v["baseline"] < v["sota"] < v["upper"]):
            raise ValueError(f"anchors out of order for {case}: {v}")
    if not a.get("log_shift", 1.0) > 0:
        raise ValueError("log_shift must be positive")
    return a


def _list_streams() -> list:
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text())
    return [f"s{s}" for s in manifest["seeds"]]


def _stage_submission() -> Path:
    """Copy the submission to a nobody-readable staging dir (never trust the
    snapshot's own permission bits)."""
    stage = Path(tempfile.mkdtemp(prefix="stage_"))
    dst = stage / "main"
    shutil.copytree(SUBMISSION_DIR, dst)
    for p in [dst, *dst.rglob("*")]:
        try:
            p.chmod(0o755 if p.is_dir() else 0o644)
        except OSError:
            pass
    return dst


def _reward(m: float, B: float, S: float, U: float, shift: float) -> float:
    def u(v: float) -> float:
        return math.log(v + shift)
    if m <= B:
        return 0.0
    if m <= S:
        return 0.60 * (u(m) - u(B)) / (u(S) - u(B))
    return min(1.0, 0.60 + 0.40 * (u(m) - u(S)) / (u(U) - u(S)))


def _run_stream_with_deadline(client, seed, out_dir):
    def _on_alarm(signum, frame):  # noqa: ARG001
        raise _StreamTimeout()
    old = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(int(TIME_BUDGET_SEC + GRACE_SEC))
    try:
        return run_stream_isolated(client, seed, str(DATA_ROOT),
                                   str(out_dir), f"ver-s{seed}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def main() -> None:
    REWARD_DIR.mkdir(parents=True, exist_ok=True)
    details: dict = {"cases": {}, "errors": []}
    reward = 0.0
    metric = None
    client = None
    try:
        anchors = _load_anchors()
        streams = _list_streams()
        seeds = [int(s[1:]) for s in streams]
        missing = [s for s in streams if s not in anchors["cases"]]
        if missing:
            raise KeyError(f"no anchors for streams {missing}")
        staged = _stage_submission()

        # compose a config once inside the data cwd so dataset paths resolve;
        # the decision server only needs solver/experiment fields from it
        cwd = os.getcwd()
        os.chdir(DATA_ROOT)
        try:
            init_cfg = compose_config(seeds[0])
        finally:
            os.chdir(cwd)

        client = DecisionClient(
            str(staged / "solver.py"), server_script=str(SERVER),
            drop_uid=SOLVER_UID, drop_gid=SOLVER_GID, config=init_cfg,
            log=lambda m: print(m, file=sys.stderr))

        with tempfile.TemporaryDirectory(prefix="nfv_out_") as tmp:
            out_dir = Path(tmp)
            rewards, metrics = [], []
            for seed in seeds:
                s = f"s{seed}"
                a = anchors["cases"][s]
                brk, m_val, r, raw = None, None, 0.0, None
                try:
                    with tempfile.TemporaryDirectory(prefix=f"stream_{seed}_") as sdir:
                        raw = _run_stream_with_deadline(client, seed, sdir)
                    (out_dir / f"{s}.json").write_text(json.dumps(raw, indent=2))
                except _StreamTimeout:
                    details["errors"].append(f"{s}: soft deadline hit")
                except Exception as exc:  # noqa: BLE001 — submission-side failure
                    details["errors"].append(f"{s}: {exc}")
                if raw is not None:
                    try:
                        m_val, brk = scorer.score_case_detailed(out_dir / f"{s}.json")
                        r = _reward(m_val, a["baseline"], a["sota"], a["upper"],
                                    anchors.get("log_shift", 1.0))
                    except Exception as exc:  # noqa: BLE001
                        details["errors"].append(f"{s}: {exc}")
                        m_val, r = None, 0.0
                details["cases"][s] = {
                    "metric": (round(m_val, 6) if m_val is not None else None),
                    "reward": round(r, 6),
                    "baseline": a["baseline"], "sota": a["sota"], "upper": a["upper"],
                    "weak_documented": a.get("weak"),
                    "breakdown": brk,
                }
                rewards.append(r)
                if m_val is not None:
                    metrics.append(m_val)

        reward = sum(rewards) / len(rewards)
        metric = sum(metrics) / len(metrics) if len(metrics) == len(streams) else None
        details["correctness"] = len(metrics) == len(streams)
        details["isolation"] = {
            "request_timeouts": client.timeouts,
            "decision_server_restarts": client.restart_count,
        }
    except Exception as exc:  # noqa: BLE001 — GRADER-side failure
        reward, metric = 0.0, None
        details["errors"].append(f"{GRADER_FAIL}{type(exc).__name__}: {exc}")
        details["correctness"] = False
    finally:
        if client is not None:
            client.close()

    payload = {"reward": round(reward, 6),
               "mean_score": float(metric) if metric is not None else 0.0}
    # Strict Harbor readers (e.g. RSI-Harness) reject a reward.json whose values
    # are not ALL numeric — reserve any "error" key for GRADER-side failures only.
    grader_error = next(
        (e for e in details["errors"] if e.startswith(GRADER_FAIL)), None)
    if grader_error is not None:
        payload["error"] = grader_error
    (REWARD_DIR / "reward.json").write_text(json.dumps(payload))
    (REWARD_DIR / "reward.txt").write_text(f"{round(reward, 6)}\n")
    (REWARD_DIR / "score_details.json").write_text(json.dumps(details, indent=2))
    print(json.dumps({"reward": payload["reward"], "mean_score": payload["mean_score"],
                      "errors": details["errors"]}))


if __name__ == "__main__":
    main()
