#!/usr/bin/env bash
# Regenerate the pinned, hashed requirement locks — Spec 05 Phase 8.
#
#   ./scripts/compile_requirements.sh
#
# `requirements/*.txt` are the hand-edited inputs: names and lower bounds.
# `requirements/lock/*.txt` are what actually gets installed. The gap between
# them is the whole point: a lower-bound-only input lets a rebuild resolve a
# different tree with nothing in the diff to review, and that is not
# hypothetical here — on 2026-11-04 a fresh build pulled a kombu whose Redis
# transport imports `packaging`, and `worker` and `beat` crash-looped while the
# image already running kept working. The only clue was in the container logs.
#
# `--universal` resolves once for every operating system, architecture and
# Python version, so the same lock installs on the arm64/py3.12 production image,
# the x86_64/py3.10 CI runner, and a developer's machine — one file, no drift
# between environments. `--generate-hashes` makes pip verify every artefact it
# downloads, so a substituted or tampered package fails the install instead of
# running.
#
# Run this whenever a `requirements/*.txt` input changes, and commit the result.
# `tests/test_dependencies.py` fails if a lock and its input drift apart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${BACKEND_DIR}"

UV="${UV:-uv}"
# The floor of the supported range; `--universal` forks upward from here.
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"

if ! command -v "${UV}" >/dev/null 2>&1; then
  echo "error: '${UV}' not found. Install uv: https://docs.astral.sh/uv/" >&2
  exit 1
fi

mkdir -p requirements/lock
for name in dev prod; do
  echo "==> compiling requirements/${name}.txt -> requirements/lock/${name}.txt"
  "${UV}" pip compile "requirements/${name}.txt" \
    --universal \
    --generate-hashes \
    --python-version "${PYTHON_VERSION}" \
    -o "requirements/lock/${name}.txt"
done

echo "Locks written. Commit requirements/lock/*.txt."
