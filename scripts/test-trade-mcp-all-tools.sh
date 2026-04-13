#!/usr/bin/env bash
# ==============================================================================
# 执行 trade-mcp 全部 MCP 工具方法的冒烟测试（JUnit，Mock 下游 HTTP）
# ==============================================================================
# 依赖：JDK 17+、Maven 3.6+
# 用法（在仓库根目录）：
#   bash scripts/test-trade-mcp-all-tools.sh
# ==============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/trade-mcp"

echo "[test-trade-mcp-all-tools] Running AllMcpToolsSmokeTest in trade-mcp..."
mvn -q test -Dtest=AllMcpToolsSmokeTest

echo "[test-trade-mcp-all-tools] OK."
