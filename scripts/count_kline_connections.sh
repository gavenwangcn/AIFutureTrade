#!/bin/bash
# ============================================================================
# 快速统计 K线监听连接数量脚本
# 
# 功能：
# 1. 快速统计连接数量
# 2. 计算symbol数量
# 3. 显示简要信息
# 
# 使用方法：
#   chmod +x scripts/count_kline_connections.sh
#   ./scripts/count_kline_connections.sh
# ============================================================================

set -e

# Binance WebSocket 服务器地址
BINANCE_HOST="fstream.binance.com"

# 查找 data_agent 进程
PID=$(pgrep -f "data_agent.py" | head -1)

if [ -z "$PID" ]; then
    echo "❌ 未找到 data_agent 进程"
    exit 1
fi

# 获取连接统计
TOTAL_CONN=$(ss -tnp 2>/dev/null | grep "pid=$PID" | wc -l)
BINANCE_CONN=$(ss -tnp 2>/dev/null | grep "pid=$PID" | grep "$BINANCE_HOST" | wc -l)
ESTAB_CONN=$(ss -tnp state established 2>/dev/null | grep "pid=$PID" | grep "$BINANCE_HOST" | wc -l)

# 计算symbol数量
SYMBOL_COUNT=0
REMAINDER=0
if [ $ESTAB_CONN -gt 0 ]; then
    SYMBOL_COUNT=$((ESTAB_CONN / 7))
    REMAINDER=$((ESTAB_CONN % 7))
fi

# 输出结果
echo "=========================================="
echo "K线监听连接统计"
echo "=========================================="
echo "进程ID: $PID"
echo "总TCP连接数: $TOTAL_CONN"
echo "到 Binance 连接数: $BINANCE_CONN"
echo "已建立连接数: $ESTAB_CONN"
echo "估计symbol数: $SYMBOL_COUNT"
echo ""

if [ $REMAINDER -gt 0 ]; then
    echo "⚠️  注意: 连接数不是7的倍数，余数: $REMAINDER"
    echo "   可能有些interval未建立连接"
fi

echo "=========================================="

