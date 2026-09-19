# virne (heuristics-only vendored build)

Vendored from the author's virne fork (upstream: https://github.com/GeminiLight/virne,
ICLR 2026 benchmark, Apache-2.0) with the learning stack removed:

- `virne/solver/learning/` deleted; `solver/__init__.py` patched accordingly
- `system/base_system.py`: RL branch of `ready()` removed (unreachable by construction)
- `utils/dataset.py`: torch import guarded (torch absent in this build)
- `network/dataset_generator.py`: vestigial `from torch import seed` dropped
- `pyproject.toml`: dependencies trimmed to the heuristic core (no torch /
  torch_geometric / tensorboard / wandb / scikit-learn)

All task anchors were measured on exactly this code (see ../README.md).

## Task-level change vs upstream (2026-09-01)

`solver.shortest_method` default changed **k_shortest → available_shortest**
(`virne/configs/main.yaml`). The task author's call: residual-graph routing is the
sane default for everyone — starter, baselines and submissions alike — so the task
measures embedding intelligence, not infrastructure-discovery luck. All anchors are
(re-)measured under this default.
