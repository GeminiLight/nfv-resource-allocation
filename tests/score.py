"""Per-stream SCORING adapter — trusted side.

The metric itself (long-term time-averaged revenue) is computed by virne's trusted
Recorder inside the child; this adapter reads the child's per-stream json, applies
sanity checks a tampered submission should not pass, and returns (score, breakdown).
Breakdown lands in verifier/score_details.json and never reaches the agent.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# sanity bounds on the metric: revenue of ALL requests accepted nonstop on a fresh
# substrate is bounded by ~2e4 per time unit at this load; anything outside is
# treated as a broken/tampered run, not a score.
MAX_PLAUSIBLE_REVENUE = 1e6
MAX_PLAUSIBLE_ACCEPTANCE = 1.0 + 1e-6


def score_case(stream_json: Path) -> float:
    return score_case_detailed(stream_json)[0]


def score_case_detailed(stream_json: Path) -> tuple[float, dict]:
    d = json.loads(stream_json.read_text())
    m = d.get("mean_score")
    if m is None:
        raise ValueError(f"no usable run: {d.get('error', 'unknown')}")
    if not math.isfinite(m) or m < 0 or m > MAX_PLAUSIBLE_REVENUE:
        raise ValueError(f"implausible mean_score {m}")
    ac = d.get("acceptance_rate", 0.0)
    if not (0.0 <= ac <= MAX_PLAUSIBLE_ACCEPTANCE):
        raise ValueError(f"implausible acceptance {ac}")
    breakdown = {
        "acceptance_rate": ac,
        "avg_r2c_ratio": d.get("avg_r2c_ratio"),
        "long_term_r2c_ratio": d.get("long_term_r2c_ratio"),
        "clock_running_time": d.get("clock_running_time"),
    }
    return float(m), breakdown
