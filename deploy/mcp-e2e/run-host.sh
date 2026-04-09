#!/usr/bin/env bash
# 在 Ubuntu 24 宿主机直接运行（需 python3），不依赖 Docker。
# 用法：在仓库根目录或本目录执行
#   source deploy/mcp-e2e/env.example   # 或你自己的 .env
#   bash deploy/mcp-e2e/run-host.sh
# 或：
#   set -a && source deploy/mcp-e2e/.env && set +a && bash deploy/mcp-e2e/run-host.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BACKEND_BASE_URL="${BACKEND_BASE_URL:-http://154.89.148.172:5002}"
if [[ -z "${BINANCE_SERVICE_LIST:-}" ]]; then
  echo "WARN: BINANCE_SERVICE_LIST 未设置，将使用 env.example 中的默认值（与 config.py 对齐）" >&2
  # shellcheck disable=SC1091
  set -a
  # shellcheck source=/dev/null
  source "$DIR/env.example" 2>/dev/null || true
  set +a
fi
exec python3 "$DIR/mcp_e2e.py"
