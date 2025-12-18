# 使用AdoptOpenJDK 11作为基础镜像
FROM adoptopenjdk:11-jre-hotspot

# 设置工作目录
WORKDIR /app

# 复制构建好的jar文件到工作目录
COPY target/java-backend-1.0.0.jar app.jar

# 暴露服务端口
EXPOSE 8080

# 设置JVM参数
ENV JAVA_OPTS="-Xms512m -Xmx1024m"

# 启动应用
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
