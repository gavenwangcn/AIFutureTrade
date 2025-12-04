# Akshare数据API项目

基于FastAPI和akshare构建的股票数据API服务。

## 项目结构

```
uv_api_project/
├── main.py          # FastAPI应用主文件
├── run.py           # 启动脚本
├── requirements.txt # 项目依赖
└── README.md        # 项目说明
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

```bash
python run.py
```

服务将在 `http://127.0.0.1:8000` 上运行。

## API接口

### 1. 搜索股票代码

```
GET /api/search_symbols
```

参数:
- `search` (可选): 搜索关键词

### 2. 获取历史K线数据

```
POST /api/history_kline
```

参数:
- `symbol` (必需): 股票代码
- `period` (可选): 周期 (1, 5, 15, 30, 60, daily, weekly, monthly)，默认为 daily

请求体格式: JSON

```json
{
  "symbol": "000001",
  "period": "daily"
}
```

### 3. 获取指数历史K线数据

```
POST /api/index_history_kline
```

参数:
- `symbol` (必需): 指数代码
- `period` (可选): 周期 (daily, weekly, monthly)，默认为 daily

请求体格式: JSON

```json
{
  "symbol": "000001",
  "period": "daily"
}
```

### 4. 健康检查

```
GET /health
```

## 使用示例

### 获取平安银行的历史数据

```bash
curl -X POST http://127.0.0.1:8000/api/history_kline \
  -H "Content-Type: application/json" \
  -d '{"symbol": "000001", "period": "daily"}'
```

### 获取上证指数的历史数据

```bash
curl -X POST http://127.0.0.1:8000/api/index_history_kline \
  -H "Content-Type: application/json" \
  -d '{"symbol": "000001", "period": "daily"}'
```

### 搜索股票

```bash
curl "http://127.0.0.1:8000/api/search_symbols?search=银行"
```