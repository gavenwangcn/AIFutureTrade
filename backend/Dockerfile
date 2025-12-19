# ============ 后端服务Dockerfile ============
# Java Spring Boot后端服务（真正的Backend API服务）
# 使用5002端口，供前端调用

# 多阶段构建：第一阶段构建JAR文件
FROM maven:3.8.6-openjdk-11-slim AS builder

WORKDIR /app

# 复制pom.xml和源代码
COPY pom.xml .
COPY src ./src

# 构建应用（跳过测试以加快构建速度）
RUN mvn clean package -DskipTests

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
