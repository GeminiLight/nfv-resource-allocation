# VERIFIER image — same vendored build; ships the SEALED held-out streams and
# the trusted decision-isolation grader. Held-out lands ONLY here, never in the
# agent image, and is readable by root ONLY: the privilege-dropped decision
# server never needs it (it receives per-request snapshots over a pipe), so the
# submission can neither read the future from disk nor from its own memory.
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8
WORKDIR /tests

COPY virne-src /tmp/virne-src
RUN find /tmp/virne-src -depth \( -name build -o -name '*.egg-info' -o -name __pycache__ \) -type d -exec rm -rf {} + \
    && pip install --no-cache-dir /tmp/virne-src && rm -rf /tmp/virne-src \
    && python3 -c "from virne.solver import SolverRegistry; import virne, os; names=list(SolverRegistry.list_registered()); assert names == [], 'no solver may ship in the image: ' + str(names); assert not any(k in n for n in names for k in ('gcn','ppo','a3c','conal','seq2seq','flag','mcts_rl','rsi','nrm','pl_rank','grc','ffd','nea','rw_rank','joint_pr','rank_bfs','ego','meta','mip','round')); assert not os.path.exists(os.path.join(os.path.dirname(virne.__file__), 'solver', 'heuristic', 'rsi_search.py')), 'LEAK: strong-reference module shipped'"

# --- sealed held-out streams: same generator, same load, UNSEEN seeds ---
# ROOT-ONLY permissions: grade.py (root) runs the simulation in-process; the
# nobody-uid decision server gets snapshots over a pipe and must not be able to
# open these files.
COPY virne_task_lib.py prepare_data.py /tests/
RUN mkdir -p /tests/data && cd /tests/data \
    && PYTHONPATH=/tests python3 /tests/prepare_data.py --split heldout --data-root /tests/data \
    && chown -R root:root /tests/data && chmod -R go-rwx /tests/data \
    && rm -f /tests/prepare_data.py

# --- trusted grader + untrusted decision server (same file as the agent image;
#     the submission staging copy is made nobody-readable by grade.py at runtime) ---
COPY grade.py           /tests/grade.py
COPY decision_server.py /tests/decision_server.py
COPY score.py           /tests/score.py
COPY test.sh            /tests/test.sh
RUN  chmod +x /tests/test.sh /tests/decision_server.py
# sealed anchor table: root-owned, unreadable by the dropped solver uid.
COPY anchors.json   /tests/anchors.json
RUN  chown root:root /tests/anchors.json && chmod 0400 /tests/anchors.json \
     && chmod -R go-w /tests && chmod a+rX /tests/virne_task_lib.py /tests/grade.py \
     /tests/decision_server.py /tests/score.py /tests/test.sh
