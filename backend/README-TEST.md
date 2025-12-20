# K线数据测试说明

## 概述

本测试用于排查Binance期货API获取1m间隔K线数据时只返回3条的问题。

## 使用方法

### 方法1: 使用Docker（推荐，适用于没有JDK的服务器）

1. 设置环境变量：
```bash
export API_KEY=your_api_key
export API_SECRET=your_api_secret
```

2. 运行测试脚本：
```bash
cd backend
./test-kline.sh [symbol] [interval] [limit] [startTime] [endTime]
```

示例：
```bash
# 测试BTCUSDT的1m K线，获取100条
./test-kline.sh BTCUSDT 1m 100

# 测试指定时间范围的K线
./test-kline.sh BTCUSDT 1m 100 1623319461670 1641782889000
```

### 方法2: 直接使用Docker命令

1. 构建镜像：
```bash
cd backend
docker build -f Dockerfile.test -t aifuturetrade-kline-test .
```

2. 运行测试：
```bash
docker run --rm \
  -e API_KEY=your_api_key \
  -e API_SECRET=your_api_secret \
  aifuturetrade-kline-test \
  BTCUSDT 1m 100
```

### 方法3: 本地运行（需要JDK 11+）

1. 编译项目：
```bash
cd backend
mvn clean compile
```

2. 运行测试：
```bash
export API_KEY=your_api_key
export API_SECRET=your_api_secret

java -cp target/classes:target/dependency/* \
  com.aifuturetrade.test.KlineCandlestickDataTest \
  BTCUSDT 1m 100
```

## 参数说明

- `symbol`: 交易对符号，如 `BTCUSDT`（默认）
- `interval`: 时间间隔，如 `1m`, `5m`, `1h`, `1d` 等（默认：`1m`）
- `limit`: 返回的K线数量（默认：`100`）
- `startTime`: 起始时间戳（毫秒），可选
- `endTime`: 结束时间戳（毫秒），可选

## 输出说明

测试会输出以下信息：
- 请求参数（交易对、时间间隔、限制数量等）
- API调用耗时
- 返回的K线数量
- 前几条K线数据的详细信息
- 问题分析（如果返回数量异常）

## 问题排查

如果返回的K线数量少于预期，测试会提示可能的原因：
1. 时间范围设置不当
2. 该交易对在该时间范围内数据不足
3. SDK或API限制
4. 网络或API响应问题

## 注意事项

1. 确保API密钥有足够的权限访问市场数据API
2. 注意API的速率限制
3. 如果使用IP限制，确保服务器IP已添加到Binance白名单

