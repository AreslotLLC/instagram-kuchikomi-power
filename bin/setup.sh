#!/usr/bin/env bash
# ローカル試運転用のセットアップスクリプト。
# Cloud Routines の Setup script フィールドには、本ファイルではなく
# README の Step 1 にある1行コマンドを直接貼ってください。
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt

mkdir -p /tmp/qa_images

echo "[setup] done"
