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
RUN mvn clean package -DskipTests -B -U

# 第二阶段：运行阶段
FROM adoptopenjdk:11-jre-hotspot

# 设置工作目录
WORKDIR /app

# 从构建阶段复制JAR文件
COPY --from=builder /app/target/java-backend-1.0.0.jar app.jar

# 暴露服务端口（5002端口供前端调用）
EXPOSE 5002

# 设置JVM参数
ENV JAVA_OPTS="-Xms512m -Xmx1024m -Dserver.port=5002"

# 启动应用
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
