FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（如果需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5002

# 使用gunicorn作为生产服务器
# 开发环境可以使用: CMD ["python", "app.py"]
CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]

