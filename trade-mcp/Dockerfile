# ============ trade-mcp Dockerfile ============
# Spring AI MCP Server：账号/订单走 backend；行情/K 线走 binance-service（配置见 application.yml / BINANCE_SERVICE_LIST）
# 所有配置从 application.yml 读取，可通过环境变量覆盖
# 构建方式与 async-service 一致（多阶段 Maven + 清单校验）

# 多阶段构建：第一阶段构建 JAR 文件
FROM maven:3.9.6-eclipse-temurin-17 AS builder

WORKDIR /app

# Maven 依赖缓存优化策略：
# 1. 先只复制 pom.xml，利用 Docker 层缓存机制
# 2. 下载所有依赖到本地缓存（不编译代码）
# 3. 然后复制源代码并编译

# 第一步：只复制 pom.xml
COPY pom.xml .

# 第二步：下载依赖到本地缓存（利用 Docker 层缓存）
RUN mvn dependency:go-offline -B -DskipTests || \
    (echo "Warning: dependency:go-offline failed, trying dependency:resolve" && \
     mvn dependency:resolve -B -DskipTests)

# 第三步：复制源代码
COPY src ./src

# 第四步：构建应用
RUN mvn clean package -DskipTests -B -U || \
    (echo "Build failed, showing error details..." && \
     mvn clean package -DskipTests -U && \
     exit 1)

# 验证 JAR 文件是否存在且包含主清单属性
RUN echo "=== Verifying JAR file ===" && \
    if [ ! -f /app/target/trade-mcp-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    echo "JAR file found, checking manifest..." && \
    jar xf /app/target/trade-mcp-1.0.0.jar META-INF/MANIFEST.MF && \
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

# 设置工作目录
WORKDIR /app

# 从构建阶段复制 JAR 文件
COPY --from=builder /app/target/trade-mcp-1.0.0.jar app.jar

# 暴露服务端口（默认 8099，与 application.yml / SERVER_PORT 一致）
EXPOSE 8099

# 设置 JVM 参数（默认与 docker-compose 中 TRADE_MCP_JAVA_OPTS 对齐，可按容器规格调整）
# -Dserver.port：Spring Boot 监听端口，可被环境变量 SERVER_PORT 覆盖
# 添加 --add-opens 以缓解 Java 9+ 反射访问相关告警（与 async-service 等 Java 服务一致）
ENV JAVA_OPTS="-Xms256m -Xmx768m -Dserver.port=8099 -Dfile.encoding=UTF-8 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 多 binance-service 实例可在运行时注入，与 trade 服务相同，例如：
# ENV BINANCE_SERVICE_LIST='[{"base_url":"http://host1:5004","timeout":30},{"base_url":"http://host2:5004","timeout":30}]'

# 启动应用（所有配置从 application.yml 读取，可通过环境变量覆盖）
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
