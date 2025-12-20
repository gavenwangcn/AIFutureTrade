#!/bin/bash

# ============ K线数据测试脚本 ============
# 用于在服务器上运行K线数据测试
# 支持Docker方式运行（服务器不需要JDK）

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认参数
SYMBOL="${1:-BTCUSDT}"
INTERVAL="${2:-1m}"
LIMIT="${3:-100}"
START_TIME="${4:-}"
END_TIME="${5:-}"

# 检查环境变量
if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
    echo -e "${YELLOW}警告: 未设置API_KEY或API_SECRET环境变量${NC}"
    echo "使用方法:"
    echo "  export API_KEY=your_api_key"
    echo "  export API_SECRET=your_api_secret"
    echo "  $0 [symbol] [interval] [limit] [startTime] [endTime]"
    echo ""
    echo "示例:"
    echo "  $0 BTCUSDT 1m 100"
    echo "  $0 BTCUSDT 1m 100 1623319461670 1641782889000"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}K线数据测试${NC}"
echo -e "${GREEN}========================================${NC}"
echo "交易对: $SYMBOL"
echo "时间间隔: $INTERVAL"
echo "限制数量: $LIMIT"
if [ -n "$START_TIME" ]; then
    echo "起始时间: $START_TIME"
fi
if [ -n "$END_TIME" ]; then
    echo "结束时间: $END_TIME"
fi
echo ""

# 检查Docker是否可用
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未找到Docker命令${NC}"
    echo "请先安装Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Docker镜像名称
IMAGE_NAME="aifuturetrade-kline-test"
CONTAINER_NAME="kline-test-$(date +%s)"

echo -e "${YELLOW}构建Docker镜像...${NC}"
docker build -f Dockerfile.test -t $IMAGE_NAME .

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker镜像构建失败${NC}"
    exit 1
fi

echo -e "${GREEN}Docker镜像构建成功${NC}"
echo ""

# 构建Docker运行命令
DOCKER_CMD="docker run --rm"
DOCKER_CMD="$DOCKER_CMD -e API_KEY=$API_KEY"
DOCKER_CMD="$DOCKER_CMD -e API_SECRET=$API_SECRET"
DOCKER_CMD="$DOCKER_CMD $IMAGE_NAME"

# 添加参数
DOCKER_CMD="$DOCKER_CMD $SYMBOL $INTERVAL $LIMIT"
if [ -n "$START_TIME" ]; then
    DOCKER_CMD="$DOCKER_CMD $START_TIME"
fi
if [ -n "$END_TIME" ]; then
    DOCKER_CMD="$DOCKER_CMD $END_TIME"
fi

echo -e "${YELLOW}运行测试...${NC}"
echo ""

# 运行测试
eval $DOCKER_CMD

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}测试完成${NC}"
else
    echo -e "${RED}测试失败 (退出码: $TEST_EXIT_CODE)${NC}"
fi

exit $TEST_EXIT_CODE

