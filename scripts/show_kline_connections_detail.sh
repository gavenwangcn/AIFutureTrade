#!/bin/bash
# ============================================================================
# 显示 K线监听连接详细信息脚本
# 
# 功能：
# 1. 显示所有连接的详细信息
# 2. 按状态分组显示
# 3. 显示本地和远程地址
# 
# 使用方法：
#   chmod +x scripts/show_kline_connections_detail.sh
#   ./scripts/show_kline_connections_detail.sh
# ============================================================================

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Binance WebSocket 服务器地址
BINANCE_HOST="fstream.binance.com"

# 查找 data_agent 进程
PID=$(pgrep -f "data_agent.py" | head -1)

if [ -z "$PID" ]; then
    echo -e "${RED}❌ 未找到 data_agent 进程${NC}"
    exit 1
fi

echo "=========================================="
echo "K线监听连接详细信息"
echo "=========================================="
echo "进程ID: $PID"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 获取所有连接
CONNECTIONS=$(ss -tnp 2>/dev/null | grep "pid=$PID" | grep "$BINANCE_HOST")

if [ -z "$CONNECTIONS" ]; then
    echo -e "${YELLOW}⚠️  未找到到 Binance 的连接${NC}"
    exit 0
fi

# 统计连接数
TOTAL=$(echo "$CONNECTIONS" | wc -l)
ESTAB=$(echo "$CONNECTIONS" | grep -c "ESTAB" || echo "0")
OTHER=$((TOTAL - ESTAB))

echo "连接统计:"
echo "  - 总连接数: $TOTAL"
echo "  - 已建立: $ESTAB"
if [ $OTHER -gt 0 ]; then
    echo "  - 其他状态: $OTHER"
fi
echo ""

# 按状态分组显示
echo "=========================================="
echo "已建立的连接 (ESTABLISHED):"
echo "=========================================="

ESTAB_CONN=$(echo "$CONNECTIONS" | grep "ESTAB")
if [ -n "$ESTAB_CONN" ]; then
    echo "$ESTAB_CONN" | while read line; do
        local_addr=$(echo "$line" | awk '{print $4}')
        remote_addr=$(echo "$line" | awk '{print $5}')
        process=$(echo "$line" | awk '{print $NF}')
        
        # 提取本地端口
        local_port=$(echo "$local_addr" | awk -F: '{print $NF}')
        
        echo -e "${GREEN}✅${NC} 本地: ${BLUE}$local_addr${NC} -> 远程: ${BLUE}$remote_addr${NC}"
        echo "   进程: $process"
        echo ""
    done
else
    echo -e "${YELLOW}⚠️  没有已建立的连接${NC}"
    echo ""
fi

# 显示其他状态的连接
OTHER_CONN=$(echo "$CONNECTIONS" | grep -v "ESTAB")
if [ -n "$OTHER_CONN" ]; then
    echo "=========================================="
    echo "其他状态的连接:"
    echo "=========================================="
    
    echo "$OTHER_CONN" | while read line; do
        state=$(echo "$line" | awk '{print $1}')
        local_addr=$(echo "$line" | awk '{print $4}')
        remote_addr=$(echo "$line" | awk '{print $5}')
        
        case "$state" in
            TIME-WAIT|FIN-WAIT-*|CLOSE-WAIT)
                echo -e "${YELLOW}⚠️  [$state]${NC} 本地: $local_addr -> 远程: $remote_addr"
                ;;
            SYN-*)
                echo -e "${RED}❌ [$state]${NC} 本地: $local_addr -> 远程: $remote_addr"
                ;;
            *)
                echo "  [$state] 本地: $local_addr -> 远程: $remote_addr"
                ;;
        esac
    done
    echo ""
fi

echo "=========================================="

