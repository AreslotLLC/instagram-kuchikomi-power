#!/usr/bin/env bash
# Cloud Routines / claude.ai/code セッション専用の依存インストール。
# .claude/settings.json の SessionStart hook から呼ばれる。
# ローカル開発時は CLAUDE_CODE_REMOTE が未設定なので即終了する。

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# 既にインストール済みならスキップ(セッション再開時の高速化)
if python3 -c "import pyairtable, httpx, dotenv" >/dev/null 2>&1; then
  echo "[install_pkgs] deps already present"
else
  python3 -m pip install --quiet -r requirements.txt
  echo "[install_pkgs] deps installed"
fi

mkdir -p /tmp/qa_images
exit 0
