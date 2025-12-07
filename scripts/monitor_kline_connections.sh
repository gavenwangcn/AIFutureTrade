#!/bin/bash
# ============================================================================
# 实时监控 Data Agent K线监听连接脚本
# 
# 功能：
# 1. 实时显示K线监听连接数量和状态
# 2. 监控连接变化
# 3. 显示连接统计信息
# 
# 使用方法：
#   chmod +x scripts/monitor_kline_connections.sh
#   ./scripts/monitor_kline_connections.sh [刷新间隔秒数，默认2秒]
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Binance WebSocket 服务器地址
BINANCE_HOST="fstream.binance.com"

# 刷新间隔（秒）
REFRESH_INTERVAL=${1:-2}

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
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
# 获取连接信息
# ============================================================================

get_connection_info() {
    local pid=$1
    
    if [ -z "$pid" ]; then
        return 1
    fi
    
    # 获取连接信息
    local total_conn=$(ss -tnp 2>/dev/null | grep "pid=$pid" | wc -l)
    local binance_conn=$(ss -tnp 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | wc -l)
    local estab_conn=$(ss -tnp state established 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | wc -l)
    local other_states=$(ss -tnp 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | grep -v "ESTAB" | wc -l)
    
    # 计算symbol数量
    local symbol_count=0
    if [ $estab_conn -gt 0 ]; then
        symbol_count=$((estab_conn / 7))
    fi
    
    # 输出结果
    echo "$total_conn|$binance_conn|$estab_conn|$other_states|$symbol_count"
}

# ============================================================================
# 显示监控信息
# ============================================================================

display_monitor_info() {
    local pid=$1
    
    clear
    print_header "Data Agent K线监听连接实时监控"
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "刷新间隔: ${REFRESH_INTERVAL}秒 (按 Ctrl+C 退出)"
    echo ""
    
    if [ -z "$pid" ]; then
        print_error "未找到 data_agent 进程"
        echo ""
        echo "提示: 请确保 data_agent 正在运行"
        return 1
    fi
    
    print_info "进程ID: $pid"
    echo ""
    
    # 获取连接信息
    local conn_info=$(get_connection_info "$pid")
    if [ -z "$conn_info" ]; then
        print_error "无法获取连接信息"
        return 1
    fi
    
    local total_conn=$(echo "$conn_info" | cut -d'|' -f1)
    local binance_conn=$(echo "$conn_info" | cut -d'|' -f2)
    local estab_conn=$(echo "$conn_info" | cut -d'|' -f3)
    local other_states=$(echo "$conn_info" | cut -d'|' -f4)
    local symbol_count=$(echo "$conn_info" | cut -d'|' -f5)
    
    # 显示统计信息
    print_header "连接统计"
    echo "  - 总TCP连接数: $total_conn"
    echo "  - 到 Binance 的连接数: $binance_conn"
    echo "  - 已建立连接数 (ESTABLISHED): $estab_conn"
    
    if [ $other_states -gt 0 ]; then
        print_warning "  - 其他状态连接数: $other_states"
    fi
    
    echo ""
    
    # 显示symbol估算
    if [ $estab_conn -gt 0 ]; then
        local remainder=$((estab_conn % 7))
        print_info "Symbol估算:"
        echo "  - 估计symbol数: $symbol_count (每个symbol有7个interval)"
        echo "  - 每个interval应该有: $symbol_count 个连接"
        
        if [ $remainder -gt 0 ]; then
            print_warning "  - 注意: 连接数不是7的倍数，余数: $remainder"
        fi
    else
        print_warning "  - 当前没有已建立的连接"
    fi
    
    echo ""
    
    # 显示连接状态分布
    print_header "连接状态分布"
    local states=$(ss -tnp 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | awk '{print $1}' | sort | uniq -c)
    
    if [ -n "$states" ]; then
        echo "$states" | while read count state; do
            case "$state" in
                ESTAB)
                    print_success "$state (已建立): $count 个"
                    ;;
                TIME-WAIT|FIN-WAIT-*|CLOSE-WAIT)
                    print_warning "$state (关闭中): $count 个"
                    ;;
                SYN-*)
                    print_error "$state (连接中): $count 个"
                    ;;
                *)
                    echo "  $state: $count 个"
                    ;;
            esac
        done
    else
        print_warning "未找到连接"
    fi
    
    echo ""
    
    # 显示最近的连接列表（最多10个）
    print_header "连接列表 (最近10个)"
    local connections=$(ss -tnp 2>/dev/null | grep "pid=$pid" | grep "$BINANCE_HOST" | head -10)
    
    if [ -n "$connections" ]; then
        echo "$connections" | while read line; do
            local state=$(echo "$line" | awk '{print $1}')
            local local_addr=$(echo "$line" | awk '{print $4}')
            local remote_addr=$(echo "$line" | awk '{print $5}')
            
            case "$state" in
                ESTAB)
                    print_success "  $local_addr -> $remote_addr"
                    ;;
                *)
                    print_warning "  [$state] $local_addr -> $remote_addr"
                    ;;
            esac
        done
    else
        print_warning "未找到连接"
    fi
    
    echo ""
    echo "按 Ctrl+C 退出监控"
}

# ============================================================================
# 主执行流程
# ============================================================================

main() {
    # 检查必要命令
    if ! command -v ss > /dev/null 2>&1; then
        print_error "ss 命令未安装，请先安装: yum install iproute2 或 apt-get install iproute2"
        exit 1
    fi
    
    # 查找进程
    local pid=$(pgrep -f "data_agent.py" | head -1)
    
    if [ -z "$pid" ]; then
        print_error "未找到 data_agent 进程"
        echo ""
        echo "提示: 请确保 data_agent 正在运行"
        exit 1
    fi
    
    # 监控循环
    while true; do
        display_monitor_info "$pid"
        sleep "$REFRESH_INTERVAL"
    done
}

# 捕获 Ctrl+C
trap 'echo ""; print_info "监控已停止"; exit 0' INT

# 执行主函数
main "$@"

