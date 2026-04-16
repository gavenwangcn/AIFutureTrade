#!/bin/bash
# 供 build-and-start.sh / restart.sh / watchdog.sh source
# 使用前须已设置 BINANCE_SERVICE_DIR

if [ -z "${BINANCE_SERVICE_DIR:-}" ]; then
    echo "common-env.sh: BINANCE_SERVICE_DIR is not set" >&2
    return 1 2>/dev/null || exit 1
fi

BINANCE_JAR_FILE="${BINANCE_SERVICE_DIR}/target/binance-service-1.0.0.jar"

# 与 build-and-start.sh 原 start_service 保持一致
BINANCE_JAVA_OPTS="-Xms1g -Xmx2g \
                -XX:+UseG1GC \
                -XX:MaxGCPauseMillis=200 \
                -XX:+UseStringDeduplication \
                -XX:+OptimizeStringConcat \
                -XX:+UseCompressedOops \
                -XX:+UseCompressedClassPointers \
                -Djava.awt.headless=true \
                -Dfile.encoding=UTF-8"
