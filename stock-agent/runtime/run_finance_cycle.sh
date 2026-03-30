#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-巡检}"
SCRIPT="/home/kent/.openclaw/workspace/stock-agent/runtime/finance_monitor.py"
OPENCLAW_BIN="openclaw"
TARGET="user:ou_916239acee3df12160e5f616e2f42e79"

MSG=$(python3 "$SCRIPT" "$MODE")

$OPENCLAW_BIN message send --channel feishu --account finance --target "$TARGET" --message "$MSG"

echo "$MSG"
