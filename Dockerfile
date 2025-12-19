# ============ 后端Dockerfile ============
# Python Flask应用服务

FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制Python依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（排除frontend目录，由.dockerignore处理）
# 服务目录
COPY backend/ backend/
COPY async/ async/
COPY common/ common/
COPY trade/ trade/
COPY market/ market/

# 配置文件
COPY gunicorn_config.py ./
# SDK目录
COPY derivatives_trading_usds_futures/ derivatives_trading_usds_futures/

EXPOSE 5002

# 使用gunicorn作为生产服务器
CMD ["gunicorn", "--config", "gunicorn_config.py", "backend.app:app"]
