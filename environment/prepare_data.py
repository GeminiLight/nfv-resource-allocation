#!/usr/bin/env python3
"""Materialize the task's request streams and substrate topologies.

Same script, two splits: the agent image runs --split visible (seeds 0,1,2), the
verifier image runs --split heldout (seeds 42,137,2024). One script, two splits,
so the distributions cannot drift apart.

    python3 prepare_data.py --split visible --data-root /app/data
"""
import argparse

from virne_task_lib import materialize_split


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["visible", "heldout"], required=True)
    ap.add_argument("--data-root", required=True)
    args = ap.parse_args()
    materialize_split(args.split, args.data_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
