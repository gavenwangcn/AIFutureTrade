FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements-e2e.txt .
RUN pip install --no-cache-dir -r requirements-e2e.txt
COPY mcp_e2e.py .
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/mcp_e2e.py"]
