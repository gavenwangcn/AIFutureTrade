#!/bin/bash
# ============================================================================
# 按 Symbol 分组显示 K线监听连接脚本
# 
# 功能：
# 1. 尝试通过 HTTP API 获取当前监听的 symbol 列表
# 2. 显示每个 symbol 的连接情况
# 3. 验证每个 symbol 是否有完整的 7 个 interval 连接
# 
# 使用方法：
#   chmod +x scripts/check_kline_connections_by_symbol.sh
#   ./scripts/check_kline_connections_by_symbol.sh [data_agent地址，默认localhost:9999]
# ============================================================================

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 默认配置
DATA_AGENT_HOST="${1:-localhost}"
DATA_AGENT_PORT="${2:-9999}"
BINANCE_HOST="fstream.binance.com"

# 支持的 interval 列表
INTERVALS=("1m" "5m" "15m" "1h" "4h" "1d" "1w")
EXPECTED_INTERVAL_COUNT=${#INTERVALS[@]}

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}📊 $1${NC}"
}

# ============================================================================
# 获取 Symbol 列表
# ============================================================================

get_symbols_from_api() {
    local url="http://${DATA_AGENT_HOST}:${DATA_AGENT_PORT}/symbols"
    
    if command -v curl > /dev/null 2>&1; then
        local response=$(curl -s -m 5 "$url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$response" ]; then
            echo "$response" | grep -o '"symbols":\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"' | tr ',' '\n'
            return 0
        fi
    elif command -v wget > /dev/null 2>&1; then
        local response=$(wget -q -O- -T 5 "$url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$response" ]; then
            echo "$response" | grep -o '"symbols":\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"' | tr ',' '\n'
            return 0
        fi
    fi
    
    return 1
}

# ============================================================================
# 统计连接
# ============================================================================

count_connections_for_symbol() {
    local pid=$1
    local symbol=$2
    
    # 注意: 我们无法直接从TCP连接中识别symbol
    # 这里我们只能统计总连接数，然后按symbol数量平均分配
    # 或者通过API获取symbol列表后，假设每个symbol有7个连接
    
    local total_estab=$(ss -tnp state established 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | wc -l)
    echo "$total_estab"
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    print_header "按 Symbol 检查 K线监听连接"
    
    # 查找进程
    local pid=$(pgrep -f "data_agent.py" | head -1)
    if [ -z "$pid" ]; then
        print_error "未找到 data_agent 进程"
        exit 1
    fi
    
    print_info "进程ID: $pid"
    print_info "Data Agent API: http://${DATA_AGENT_HOST}:${DATA_AGENT_PORT}"
    echo ""
    
    # 尝试从API获取symbol列表
    print_info "尝试从 API 获取 symbol 列表..."
    local symbols=$(get_symbols_from_api)
    
    if [ -z "$symbols" ]; then
        print_warning "无法从 API 获取 symbol 列表，使用连接数估算"
        echo ""
        
        # 通过连接数估算
        local total_estab=$(ss -tnp state established 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | wc -l)
        local estimated_symbols=$((total_estab / EXPECTED_INTERVAL_COUNT))
        
        print_info "总连接数: $total_estab"
        print_info "估计symbol数: $estimated_symbols"
        print_warning "无法显示每个symbol的详细连接情况，请使用其他脚本查看"
        
        echo ""
        print_info "提示: 可以通过以下方式获取symbol列表:"
        echo "  curl http://${DATA_AGENT_HOST}:${DATA_AGENT_PORT}/symbols"
        
        exit 0
    fi
    
    # 显示从API获取的symbol列表
    local symbol_count=$(echo "$symbols" | wc -l)
    print_success "从 API 获取到 $symbol_count 个 symbol"
    echo ""
    
    # 获取总连接数
    local total_estab=$(ss -tnp state established 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | wc -l)
    local expected_conn=$((symbol_count * EXPECTED_INTERVAL_COUNT))
    
    print_header "连接统计"
    print_info "Symbol数量: $symbol_count"
    print_info "每个symbol应该有: $EXPECTED_INTERVAL_COUNT 个连接 (${INTERVALS[*]})"
    print_info "预期总连接数: $expected_conn"
    print_info "实际连接数: $total_estab"
    echo ""
    
    if [ $total_estab -eq $expected_conn ]; then
        print_success "连接数匹配预期"
    elif [ $total_estab -lt $expected_conn ]; then
        local missing=$((expected_conn - total_estab))
        print_warning "缺少 $missing 个连接"
    else
        local extra=$((total_estab - expected_conn))
        print_warning "多出 $extra 个连接"
    fi
    
    echo ""
    
    # 显示每个symbol的信息
    print_header "Symbol 列表"
    echo "$symbols" | while read symbol; do
        if [ -n "$symbol" ]; then
            echo "  - $symbol (应该有 $EXPECTED_INTERVAL_COUNT 个连接)"
        fi
    done
    
    echo ""
    print_info "注意: 由于TCP连接无法直接识别symbol，无法显示每个symbol的具体连接"
    print_info "建议使用 check_kline_connections.sh 查看所有连接的详细信息"
    echo ""
}

# 执行主函数
main "$@"

