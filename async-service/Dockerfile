# ============ Async Service Dockerfile ============
# Async Service微服务
# 所有配置从application.yml读取，可通过环境变量覆盖

# 多阶段构建：第一阶段构建JAR文件
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
    if [ ! -f /app/target/async-service-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    echo "JAR file found, checking manifest..." && \
    jar xf /app/target/async-service-1.0.0.jar META-INF/MANIFEST.MF && \
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
COPY --from=builder /app/target/async-service-1.0.0.jar app.jar

# 暴露服务端口（默认5003，实际端口由application.yml配置）
EXPOSE 5003

# 设置JVM参数（高性能优化）
# -Xms: 初始堆内存1G，-Xmx: 最大堆内存2G（允许动态调整以适应负载）
# -XX:+UseG1GC: 使用G1垃圾收集器，适合大内存和低延迟场景
# -XX:MaxGCPauseMillis: 最大GC暂停时间目标（毫秒）
# -XX:+UseStringDeduplication: 字符串去重，减少内存占用
# -XX:+OptimizeStringConcat: 优化字符串拼接
# -XX:+UseCompressedOops: 使用压缩指针，节省内存
# -XX:+UseCompressedClassPointers: 使用压缩类指针
# -Djava.awt.headless=true: 无头模式，不需要图形界面
# -Dfile.encoding=UTF-8: 文件编码
# -Dorg.eclipse.jetty.websocket.maxTextMessageSize=204800: Jetty WebSocket 最大文本消息大小（200KB）
#   币安全市场ticker数据可能较大（实际约 68KB），默认限制 65KB 不够，设置为 200KB
# 添加 --add-opens 参数以解决 Java 9+ 上的反射访问警告
# 注意：所有服务配置（包括端口）都从application.yml读取，可通过环境变量覆盖
ENV JAVA_OPTS="-Xms1g -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UseStringDeduplication -XX:+OptimizeStringConcat -XX:+UseCompressedOops -XX:+UseCompressedClassPointers -Djava.awt.headless=true -Dfile.encoding=UTF-8 -Dorg.eclipse.jetty.websocket.maxTextMessageSize=204800 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 启动应用（所有配置从application.yml读取，可通过环境变量覆盖）
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]

