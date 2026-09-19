#!/usr/bin/env bash
# Assemble the two Docker build contexts and build both images.
#
# The repo keeps a single source of truth per file (virne_task_lib.py and
# decision_server.py live in environment/), so each image's build context is
# staged into a temp dir first. This script is the canonical way to build and
# doubles as the exact reproducibility recipe.
set -euo pipefail
cd "$(dirname "$0")"

stage_agent() {
  local ctx
  ctx=$(mktemp -d /tmp/nfv-agent-ctx.XXXXXX)
  cp -R environment/virne_task_lib.py environment/prepare_data.py \
        environment/decision_server.py environment/selfcheck.py \
        environment/methods environment/Dockerfile "$ctx/"
  cp -R virne-src "$ctx/virne-src"
  echo "$ctx"
}

stage_verifier() {
  local ctx
  ctx=$(mktemp -d /tmp/nfv-verifier-ctx.XXXXXX)
  cp environment/virne_task_lib.py environment/decision_server.py "$ctx/"
  cp tests/grade.py tests/score.py tests/test.sh tests/anchors.json \
     tests/Dockerfile "$ctx/"
  cp -R tests/solution "$ctx/solution"    # author-side; used by oracle CI only
  cp -R virne-src "$ctx/virne-src"
  echo "$ctx"
}

CTX_A=$(stage_agent)
CTX_V=$(stage_verifier)
trap 'rm -rf "$CTX_A" "$CTX_V"' EXIT

docker build "$CTX_A" -t nfv-agent:latest "$@"
docker build "$CTX_V" -t nfv-verifier:latest "$@"
echo "built nfv-agent:latest and nfv-verifier:latest"
