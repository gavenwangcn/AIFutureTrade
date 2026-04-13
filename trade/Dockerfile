# ============ 交易服务Dockerfile ============
# Python Flask交易服务
# 注意：此Dockerfile位于trade目录，build context为项目根目录
#
# Override base image if docker.io is unreachable: build-arg PYTHON_IMAGE=...

ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 安装系统依赖和TA-Lib的C库依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    wget \
    make \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 下载并编译安装TA-Lib C库
# 注意：TA-Lib C库需要先安装，然后才能安装Python绑定
# 
# 缓存优化策略：
# 1. 将下载和编译步骤分离，利用Docker层缓存机制
#    如果下载的文件URL和内容没有变化，Docker会复用缓存的层，避免重复下载和编译
# 2. 可选：使用本地缓存文件加速构建（推荐）
#    步骤：
#    a) 首次构建后，从构建日志中找到下载的文件位置，或手动下载：
#       wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
#    b) 将文件放在trade目录
#    c) 取消注释下面的 COPY 行，并注释掉 wget 行
#
# 使用本地缓存文件（推荐，取消注释以启用）：
# COPY trade/ta-lib-0.4.0-src.tar.gz /tmp/ta-lib-0.4.0-src.tar.gz

# 下载 TA-Lib 源码（多 URL 回退，缓解 SourceForge / 跨境网络不稳定）
# 注意：若使用本地缓存文件，请注释本 RUN，并取消注释上方的 COPY trade/ta-lib-0.4.0-src.tar.gz
RUN set -eux; \
    f="/tmp/ta-lib-0.4.0-src.tar.gz"; \
    ok=0; \
    for url in \
      "https://downloads.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz" \
      "https://master.dl.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz" \
      "http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz"; \
    do \
      if curl -fsSL --retry 5 --retry-delay 3 --connect-timeout 30 "$url" -o "$f" && [ -s "$f" ]; then ok=1; break; fi; \
    done; \
    test "$ok" -eq 1; \
    tar -xzf "$f" -C /tmp && \
    cd /tmp/ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd / && \
    rm -rf /tmp/ta-lib "$f" && \
    ldconfig

# 复制Python依赖文件并安装
COPY trade/requirements.txt .
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -r requirements.txt

# 复制应用代码（所有Python代码已合并到trade目录）
COPY trade/ trade/

# 复制配置文件
COPY trade/gunicorn_config.py ./

EXPOSE 5000

# 使用gunicorn作为生产服务器
# 注意：由于代码已合并到trade目录，需要设置PYTHONPATH
ENV PYTHONPATH=/app
CMD ["gunicorn", "--config", "gunicorn_config.py", "trade.app:app"]
