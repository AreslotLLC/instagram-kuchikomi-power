#!/usr/bin/env bash
# Cloud Routines Environment の Setup script として登録する想定。
# Environment 起動時に1回だけ実行され、Routine 本体は素早く立ち上がる。
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt

mkdir -p /tmp/qa_images

echo "[setup] done"
