# ============ 交易服务Dockerfile ============
# Python Flask交易服务

FROM python:3.10-slim

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
#    b) 将文件放在项目根目录
#    c) 取消注释下面的 COPY 行，并注释掉 wget 行
#
# 使用本地缓存文件（推荐，取消注释以启用）：
# COPY ta-lib-0.4.0-src.tar.gz /tmp/ta-lib-0.4.0-src.tar.gz

# 下载TA-Lib源码
# 注意：如果使用本地缓存文件，请注释掉下面这行，并取消注释上面的 COPY 行
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz -O /tmp/ta-lib-0.4.0-src.tar.gz

# 解压和编译步骤（如果下载的文件没有变化，此步骤会使用Docker缓存）
RUN tar -xzf /tmp/ta-lib-0.4.0-src.tar.gz -C /tmp && \
    cd /tmp/ta-lib/ && \
    ./configure --prefix=/usr && \
    make -j$(nproc) && \
    make install && \
    cd / && \
    rm -rf /tmp/ta-lib /tmp/ta-lib-0.4.0-src.tar.gz && \
    ldconfig

# 复制Python依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（排除frontend目录，由.dockerignore处理）
# 服务目录
COPY async/ async/
COPY common/ common/
COPY trade/ trade/
COPY market/ market/

# 配置文件
COPY gunicorn_config.py ./
# SDK目录
COPY derivatives_trading_usds_futures/ derivatives_trading_usds_futures/

EXPOSE 5000

# 使用gunicorn作为生产服务器
CMD ["gunicorn", "--config", "gunicorn_config.py", "trade.app:app"]
