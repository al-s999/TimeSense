#!/usr/bin/env bash
set -euo pipefail

python -m pip uninstall -y numpy
python -m pip install "numpy<2"
python -m pip install --upgrade insightface onnxruntime
