# AGENT image — visible streams only (held-out lives solely in tests/Dockerfile).
# Python >= 3.12 required by the vendored virne build.
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8
WORKDIR /app

# --- virne: vendored heuristics-only build (learning stack removed at source;
#    no torch in the image at all — that is the fence behind the instruction's
#    "no learned models" rule) ---
COPY virne-src /tmp/virne-src
RUN find /tmp/virne-src -depth \( -name build -o -name '*.egg-info' -o -name __pycache__ \) -type d -exec rm -rf {} + \
    && pip install --no-cache-dir /tmp/virne-src && rm -rf /tmp/virne-src \
    && python3 -c "from virne.solver import SolverRegistry; names=list(SolverRegistry.list_registered()); assert names == [], 'no solver may ship in the image: ' + str(names); assert not any(k in n for n in names for k in ('gcn','ppo','a3c','conal','seq2seq','flag','mcts_rl','rsi','nrm','pl_rank','grc','ffd','nea','rw_rank','joint_pr','rank_bfs','ego','meta','mip','round')); print('solver registry empty — simulator and primitives only')"

# --- visible streams: materialized at BUILD time (the only networked moment);
#     runtime loads these files (if_load_*), never regenerates ---
COPY virne_task_lib.py prepare_data.py /app/
RUN mkdir -p /app/data && cd /app/data \
    && PYTHONPATH=/app python3 /app/prepare_data.py --split visible --data-root /app/data \
    && chmod -R a+rX /app/data

# --- editable baseline + self-check surface ---
# The decision server (which runs the submission) must be able to read this tree.
COPY methods /app/methods
RUN chmod -R a+rX /app/methods
COPY virne_task_lib.py decision_server.py selfcheck.py /app/
RUN chmod +x /app/selfcheck.py /app/decision_server.py

# Pre-install the agent CLI so [environment] can later be narrowed from public
# (docs/network-policy.md). procps is required by claude-code.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep curl bash nodejs npm ca-certificates procps git \
 && rm -rf /var/lib/apt/lists/*
