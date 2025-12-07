#!/bin/bash
# ============================================================================
# 检查 Data Agent K线监听连接脚本
# 
# 功能：
# 1. 查看所有K线监听的详细信息
# 2. 统计连接数量
# 3. 显示每个symbol的interval连接情况
# 
# 使用方法：
#   chmod +x scripts/check_kline_connections.sh
#   ./scripts/check_kline_connections.sh
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Binance WebSocket 服务器地址
BINANCE_HOST="fstream.binance.com"
BINANCE_PORT="443"

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
    echo ""
    echo "=========================================="
    echo -e "${BLUE}$1${NC}"
    echo "=========================================="
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
# 主函数
# ============================================================================

check_data_agent_process() {
    print_header "1. 检查 Data Agent 进程"
    
    # 查找 data_agent 进程
    PID=$(pgrep -f "data_agent.py" | head -1)
    
    if [ -z "$PID" ]; then
        print_error "未找到 data_agent 进程"
        echo ""
        echo "提示: 请确保 data_agent 正在运行"
        return 1
    fi
    
    print_success "找到 data_agent 进程: PID=$PID"
    echo ""
    echo "进程详细信息:"
    ps -p $PID -o pid,user,%cpu,%mem,etime,cmd --no-headers | awk '{
        printf "  - PID: %s\n", $1
        printf "  - 用户: %s\n", $2
        printf "  - CPU: %s%%\n", $3
        printf "  - 内存: %s%%\n", $4
        printf "  - 运行时间: %s\n", $5
        printf "  - 命令: %s\n", substr($0, index($0,$6))
    }'
    echo ""
    
    export DATA_AGENT_PID=$PID
    return 0
}

check_tcp_connections() {
    print_header "2. 检查 TCP 连接统计"
    
    if [ -z "$DATA_AGENT_PID" ]; then
        print_error "未找到 data_agent 进程，跳过连接检查"
        return 1
    fi
    
    # 统计所有TCP连接
    TOTAL_CONN=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | wc -l)
    
    # 统计到 Binance 的连接
    BINANCE_CONN=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST" | wc -l)
    
    # 统计已建立的连接
    ESTAB_CONN=$(ss -tnp state established 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST" | wc -l)
    
    # 统计其他状态的连接
    OTHER_STATES=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST" | grep -v "ESTAB" | wc -l)
    
    print_info "连接统计:"
    echo "  - 总TCP连接数: $TOTAL_CONN"
    echo "  - 到 Binance 的连接数: $BINANCE_CONN"
    echo "  - 已建立连接数 (ESTABLISHED): $ESTAB_CONN"
    
    if [ $OTHER_STATES -gt 0 ]; then
        print_warning "其他状态连接数: $OTHER_STATES"
    fi
    
    echo ""
    
    # 估算symbol数量（每个symbol有7个interval）
    if [ $ESTAB_CONN -gt 0 ]; then
        SYMBOL_COUNT=$((ESTAB_CONN / 7))
        REMAINDER=$((ESTAB_CONN % 7))
        
        echo "  - 估计symbol数: $SYMBOL_COUNT (每个symbol有7个interval)"
        if [ $REMAINDER -gt 0 ]; then
            print_warning "  - 注意: 连接数不是7的倍数，可能有些interval未建立连接"
        fi
    fi
    
    echo ""
    
    export TOTAL_CONN
    export BINANCE_CONN
    export ESTAB_CONN
    return 0
}

show_connection_details() {
    print_header "3. K线监听连接详细信息"
    
    if [ -z "$DATA_AGENT_PID" ]; then
        print_error "未找到 data_agent 进程，跳过详细信息"
        return 1
    fi
    
    # 获取所有到 Binance 的连接
    CONNECTIONS=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST")
    
    if [ -z "$CONNECTIONS" ]; then
        print_warning "未找到到 Binance 的连接"
        return 1
    fi
    
    echo "连接列表:"
    echo ""
    
    # 按状态分组显示
    echo "📡 已建立的连接 (ESTABLISHED):"
    echo "$CONNECTIONS" | grep "ESTAB" | while read line; do
        state=$(echo "$line" | awk '{print $1}')
        local_addr=$(echo "$line" | awk '{print $4}')
        remote_addr=$(echo "$line" | awk '{print $5}')
        process=$(echo "$line" | awk '{print $NF}')
        
        # 提取本地端口
        local_port=$(echo "$local_addr" | awk -F: '{print $NF}')
        
        print_success "  本地: $local_addr -> 远程: $remote_addr"
        echo "      进程: $process"
        echo ""
    done
    
    # 显示其他状态的连接
    OTHER_CONN=$(echo "$CONNECTIONS" | grep -v "ESTAB")
    if [ -n "$OTHER_CONN" ]; then
        echo "⚠️  其他状态的连接:"
        echo "$OTHER_CONN" | while read line; do
            state=$(echo "$line" | awk '{print $1}')
            local_addr=$(echo "$line" | awk '{print $4}')
            remote_addr=$(echo "$line" | awk '{print $5}')
            
            print_warning "  [$state] 本地: $local_addr -> 远程: $remote_addr"
        done
        echo ""
    fi
}

show_connection_by_state() {
    print_header "4. 连接状态分布"
    
    if [ -z "$DATA_AGENT_PID" ]; then
        print_error "未找到 data_agent 进程，跳过状态检查"
        return 1
    fi
    
    # 统计各状态的连接数
    STATES=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST" | awk '{print $1}' | sort | uniq -c)
    
    if [ -z "$STATES" ]; then
        print_warning "未找到连接"
        return 1
    fi
    
    echo "$STATES" | while read count state; do
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
    echo ""
}

show_connection_summary() {
    print_header "5. 连接汇总信息"
    
    if [ -z "$ESTAB_CONN" ] || [ "$ESTAB_CONN" -eq 0 ]; then
        print_warning "没有已建立的连接"
        return 1
    fi
    
    # 计算统计信息
    SYMBOL_COUNT=$((ESTAB_CONN / 7))
    REMAINDER=$((ESTAB_CONN % 7))
    
    print_info "汇总:"
    echo "  - 已建立的K线监听连接: $ESTAB_CONN 个"
    echo "  - 估计symbol数量: $SYMBOL_COUNT 个"
    echo "  - 每个symbol应该有: 7 个连接 (7个interval)"
    echo "  - Interval列表: 1m, 5m, 15m, 1h, 4h, 1d, 1w"
    
    if [ $REMAINDER -gt 0 ]; then
        print_warning "  - 注意: 连接数不是7的倍数，可能有些interval未建立连接"
        echo "  - 余数: $REMAINDER 个连接"
    fi
    
    echo ""
    
    # 显示每个interval的预期连接数
    if [ $SYMBOL_COUNT -gt 0 ]; then
        echo "  - 每个interval应该有: $SYMBOL_COUNT 个连接"
    fi
    
    echo ""
}

check_network_connectivity() {
    print_header "6. 网络连通性检查"
    
    # 检查 Binance 服务器是否可达
    print_info "检查 Binance WebSocket 服务器连通性..."
    
    if ping -c 3 -W 2 "$BINANCE_HOST" > /dev/null 2>&1; then
        print_success "Binance 服务器 ($BINANCE_HOST) 可达"
    else
        print_error "Binance 服务器 ($BINANCE_HOST) 不可达"
    fi
    
    # 检查端口连通性
    if command -v nc > /dev/null 2>&1; then
        if nc -zv -w 2 "$BINANCE_HOST" "$BINANCE_PORT" > /dev/null 2>&1; then
            print_success "端口 $BINANCE_PORT 可达"
        else
            print_error "端口 $BINANCE_PORT 不可达"
        fi
    else
        print_warning "nc 命令未安装，跳过端口检查"
    fi
    
    echo ""
}

show_detailed_connection_table() {
    print_header "7. 详细连接表"
    
    if [ -z "$DATA_AGENT_PID" ]; then
        print_error "未找到 data_agent 进程"
        return 1
    fi
    
    # 获取所有连接并格式化输出
    CONNECTIONS=$(ss -tnp 2>/dev/null | grep "pid=$DATA_AGENT_PID" | grep "$BINANCE_HOST")
    
    if [ -z "$CONNECTIONS" ]; then
        print_warning "未找到连接"
        return 1
    fi
    
    echo "格式: [状态] 本地地址:端口 -> 远程地址:端口 [进程信息]"
    echo ""
    printf "%-12s %-25s %-30s %s\n" "状态" "本地地址" "远程地址" "进程"
    echo "------------------------------------------------------------------------------------------------"
    
    echo "$CONNECTIONS" | while read line; do
        state=$(echo "$line" | awk '{print $1}')
        local_addr=$(echo "$line" | awk '{print $4}')
        remote_addr=$(echo "$line" | awk '{print $5}')
        process=$(echo "$line" | awk '{print $NF}')
        
        # 格式化状态显示
        case "$state" in
            ESTAB)
                state_display="${GREEN}ESTAB${NC}"
                ;;
            *)
                state_display="${YELLOW}$state${NC}"
                ;;
        esac
        
        printf "%-12s %-25s %-30s %s\n" "$state_display" "$local_addr" "$remote_addr" "$process"
    done
    
    echo ""
}

# ============================================================================
# 主执行流程
# ============================================================================

main() {
    clear
    echo "=========================================="
    echo "  Data Agent K线监听连接检查工具"
    echo "=========================================="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # 检查必要命令
    if ! command -v ss > /dev/null 2>&1; then
        print_error "ss 命令未安装，请先安装: yum install iproute2 或 apt-get install iproute2"
        exit 1
    fi
    
    # 执行检查
    if check_data_agent_process; then
        check_tcp_connections
        show_connection_details
        show_connection_by_state
        show_connection_summary
        show_detailed_connection_table
        check_network_connectivity
    else
        print_error "无法继续检查，因为未找到 data_agent 进程"
        exit 1
    fi
    
    echo "=========================================="
    echo "检查完成"
    echo "=========================================="
    echo ""
}

# 执行主函数
main "$@"

