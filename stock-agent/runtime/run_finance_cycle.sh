#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-巡检}"
SCRIPT="/home/kent/.openclaw/workspace/stock-agent/runtime/finance_monitor.py"
OPENCLAW_BIN="openclaw"
TARGET="user:ou_916239acee3df12160e5f616e2f42e79"
VENV_PY="/home/kent/.openclaw/workspace/stock-agent/.venv/bin/python"

if [ -x "$VENV_PY" ]; then
  PY_BIN="$VENV_PY"
else
  PY_BIN="python3"
fi

MSG=$($PY_BIN "$SCRIPT" "$MODE")

$OPENCLAW_BIN message send --channel feishu --account finance --target "$TARGET" --message "$MSG"

echo "$MSG"
