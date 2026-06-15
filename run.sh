#!/bin/bash
cd "$(dirname "$0")"
# Google Cloud SDK (если установлен через scripts/setup_google_cloud.sh)
export CLOUDSDK_PYTHON="${CLOUDSDK_PYTHON:-$HOME/miniconda3/bin/python}"
export PATH="$HOME/google-cloud-sdk/bin:${PATH}"
if [ -x ".venv-py311/bin/python" ] && .venv-py311/bin/python - <<'PY' >/dev/null 2>&1
import importlib.metadata as md
import sys

try:
    major = int(md.version("numpy").split(".", 1)[0])
except Exception:
    sys.exit(1)

# numpy 1.26.x can crash on this macOS/Accelerate stack during import.
sys.exit(0 if major >= 2 else 1)
PY
then
  source .venv-py311/bin/activate
else
  source .venv/bin/activate
fi
exec python -m bot.main
