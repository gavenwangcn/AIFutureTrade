# ============ Binance Service Dockerfile ============
# Binance Service微服务
# 使用5004端口

# 多阶段构建：第一阶段构建JAR文件
FROM maven:3.8.6-openjdk-17-slim AS builder

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
    if [ ! -f /app/target/binance-service-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    echo "JAR file found, checking manifest..." && \
    jar xf /app/target/binance-service-1.0.0.jar META-INF/MANIFEST.MF && \
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

# 从构建阶段复制JAR文件
COPY --from=builder /app/target/binance-service-1.0.0.jar app.jar

# 暴露服务端口（5004端口）
EXPOSE 5004

# 设置JVM参数
# 添加 --add-opens 参数以解决 Java 9+ 上的反射访问警告
ENV JAVA_OPTS="-Xms512m -Xmx1024m -Dserver.port=5004 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 启动应用
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]

