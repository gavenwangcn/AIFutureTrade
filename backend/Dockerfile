# ============ 后端服务Dockerfile ============
# Java Spring Boot后端服务（真正的Backend API服务）
# 使用5002端口，供前端调用

# 多阶段构建：第一阶段构建JAR文件
FROM maven:3.8.6-openjdk-11-slim AS builder

WORKDIR /app

# Maven 依赖缓存优化策略：
# 1. 先只复制 pom.xml，利用 Docker 层缓存机制
#    如果 pom.xml 没有变化，Docker 会复用缓存的依赖层，避免重新下载
# 2. 下载所有依赖到本地缓存（不编译代码）
#    使用 dependency:go-offline 或 dependency:resolve 下载依赖
# 3. 然后复制源代码并编译
#    这样只有源代码变化时才重新编译，依赖已经缓存在 Docker 层中

# 第一步：只复制 pom.xml
COPY pom.xml .

# 第二步：下载依赖到本地缓存（利用 Docker 层缓存）
# 如果 pom.xml 没有变化，这一步会使用 Docker 缓存的层，不会重新下载依赖
# -B: 批处理模式，不显示进度条
# -DskipTests: 跳过测试（依赖解析阶段不需要运行测试）
# dependency:go-offline: 下载所有依赖和插件到本地仓库
# 注意：如果 dependency:go-offline 失败，会回退到 dependency:resolve
RUN mvn dependency:go-offline -B -DskipTests || \
    (echo "Warning: dependency:go-offline failed, trying dependency:resolve" && \
     mvn dependency:resolve -B -DskipTests)

# 第三步：复制源代码（源代码变化时才会重新编译）
COPY src ./src

# 第四步：构建应用（跳过测试以加快构建速度）
# 此时依赖已经在本地缓存中，不需要重新下载
# -U: 不检查更新（使用缓存的依赖）
# -B: 批处理模式
# -DskipTests: 跳过测试
# 注意：mvn package 会自动执行 spring-boot:repackage，生成可执行的 JAR 文件
# 使用 -X 参数显示详细日志，便于调试（如果需要可以移除 -B 来显示进度）
RUN mvn clean package -DskipTests -B -U || \
    (echo "Build failed, showing error details..." && \
     mvn clean package -DskipTests -U && \
     exit 1)

# 验证 JAR 文件是否存在且包含主清单属性
# 使用 Java 自带的 jar 命令来检查清单文件（不需要安装额外的工具）
RUN echo "=== Verifying JAR file ===" && \
    if [ ! -f /app/target/java-backend-1.0.0.jar ]; then \
        echo "ERROR: JAR file not found. Available files:" && \
        ls -lh /app/target/ && \
        exit 1; \
    fi && \
    echo "JAR file found, checking manifest..." && \
    jar xf /app/target/java-backend-1.0.0.jar META-INF/MANIFEST.MF && \
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
FROM adoptopenjdk:11-jre-hotspot

# 设置工作目录
WORKDIR /app

# 从构建阶段复制JAR文件
# Spring Boot Maven 插件会生成可执行的 JAR 文件（包含所有依赖）
# 文件名格式：{artifactId}-{version}.jar
# 注意：如果构建失败，可以检查 target 目录中的实际文件名
COPY --from=builder /app/target/java-backend-1.0.0.jar app.jar

# 暴露服务端口（5002端口供前端调用）
EXPOSE 5002

# 设置JVM参数
# 添加 --add-opens 参数以解决 MyBatis-Plus 在 Java 9+ 上的反射访问警告
ENV JAVA_OPTS="-Xms512m -Xmx1024m -Dserver.port=5002 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"

# 启动应用
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
