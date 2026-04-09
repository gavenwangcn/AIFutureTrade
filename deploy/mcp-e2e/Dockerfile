# Ubuntu 24 / 任意宿主机均可：仅依赖 Python 3 标准库
FROM python:3.12-alpine
WORKDIR /app
COPY mcp_e2e.py .
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/mcp_e2e.py"]
