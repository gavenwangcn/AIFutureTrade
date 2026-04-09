# syntax=docker/dockerfile:1
# ============ trade-mcp Dockerfile ============
# Spring Boot MCP Server：账号/订单走 Java backend；行情/K 线走 binance-service（支持多实例，见 application.yml / BINANCE_SERVICE_LIST）
# 构建示例（在项目根目录）：
#   docker build -f trade-mcp/Dockerfile ./trade-mcp
# 启用依赖缓存（推荐）：
#   DOCKER_BUILDKIT=1 docker build -f trade-mcp/Dockerfile ./trade-mcp

FROM maven:3.9.6-eclipse-temurin-17 AS builder

WORKDIR /app

COPY pom.xml .

RUN --mount=type=cache,target=/root/.m2/repository \
    mvn dependency:go-offline -B -DskipTests || \
    (echo "Warning: dependency:go-offline failed, trying dependency:resolve" && \
     mvn dependency:resolve -B -DskipTests)

COPY src ./src

RUN --mount=type=cache,target=/root/.m2/repository \
    mvn clean package -DskipTests -B || \
    (echo "Build failed, showing error details..." && \
     mvn clean package -DskipTests && \
     exit 1)

RUN echo "=== Verifying JAR file ===" && \
    if [ ! -f /app/target/trade-mcp-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    jar xf /app/target/trade-mcp-1.0.0.jar META-INF/MANIFEST.MF && \
    if grep -q "Main-Class" META-INF/MANIFEST.MF; then \
        grep "Main-Class" META-INF/MANIFEST.MF && \
        rm -rf META-INF && \
        echo "JAR file verification passed"; \
    else \
        echo "ERROR: JAR file missing Main-Class in manifest" && \
        cat META-INF/MANIFEST.MF && \
        rm -rf META-INF && \
        exit 1; \
    fi

FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --from=builder /app/target/trade-mcp-1.0.0.jar app.jar

# 默认与 application.yml 中 server.port 一致
EXPOSE 8099

# JVM：可按容器规格调整；-Dserver.port 可被环境变量 SERVER_PORT 覆盖（Spring Boot）
ENV JAVA_OPTS="-Xms256m -Xmx768m -Dserver.port=8099 -Dfile.encoding=UTF-8 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 多 binance-service 可在运行时注入，与 trade 服务相同：
# ENV BINANCE_SERVICE_LIST='[{"base_url":"http://host1:5004","timeout":30},{"base_url":"http://host2:5004","timeout":30}]'
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
