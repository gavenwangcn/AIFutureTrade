#!/usr/bin/env bash
# Ubuntu / 本机：先 pip install -r requirements-e2e.txt，再执行本脚本。
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TRADE_MCP_BASE_URL="${TRADE_MCP_BASE_URL:-http://127.0.0.1:8099}"
cd "$DIR"
exec python3 mcp_e2e.py
