# syntax=docker/dockerfile:1
# ============ Trade Monitor Service Dockerfile ============
# Trade Monitor Service - 交易监控告警服务
# 所有配置从application.yml读取，可通过环境变量覆盖
# 构建时需启用 BuildKit：DOCKER_BUILDKIT=1 docker compose build trade-monitor

# 多阶段构建：第一阶段构建JAR文件
FROM maven:3.9.6-eclipse-temurin-17 AS builder

WORKDIR /app

# Maven 依赖缓存优化策略
COPY pom.xml .

# 下载依赖到缓存
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn dependency:go-offline -B -DskipTests || \
    (echo "Warning: dependency:go-offline failed, trying dependency:resolve" && \
     mvn dependency:resolve -B -DskipTests)

# 复制源代码
COPY src ./src

# 构建应用
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn clean package -DskipTests -B || \
    (echo "Build failed, showing error details..." && \
     mvn clean package -DskipTests && \
     exit 1)

# 验证 JAR 文件
RUN echo "=== Verifying JAR file ===" && \
    if [ ! -f /app/target/trade-monitor-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    echo "JAR file found, checking manifest..." && \
    jar xf /app/target/trade-monitor-1.0.0.jar META-INF/MANIFEST.MF && \
    if grep -q "Main-Class" META-INF/MANIFEST.MF; then \
        echo "Main-Class found in manifest:" && \
        grep "Main-Class" META-INF/MANIFEST.MF && \
        rm -rf META-INF && \
        echo "JAR file verification passed"; \
    else \
        echo "ERROR: JAR file missing Main-Class in manifest" && \
        echo "Manifest content:" && \
        cat META-INF/MANIFEST.MF && \
        rm -rf META-INF && \
        exit 1; \
    fi

# 第二阶段：运行阶段
FROM eclipse-temurin:17-jre

WORKDIR /app

# 从构建阶段复制JAR文件
COPY --from=builder /app/target/trade-monitor-1.0.0.jar app.jar

# 暴露服务端口
EXPOSE 5005

# 设置JVM参数
ENV JAVA_OPTS="-Xms512m -Xmx1024m -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UseStringDeduplication -XX:+OptimizeStringConcat -XX:+UseCompressedOops -XX:+UseCompressedClassPointers -Djava.awt.headless=true -Dfile.encoding=UTF-8 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 启动应用
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
