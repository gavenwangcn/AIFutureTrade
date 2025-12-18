## 1. 项目结构设计

创建java_backend目录，并按照三层架构设计项目结构：

```
java_backend/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/
│   │   │       └── aifuturetrade/
│   │   │           ├── controller/          # 控制器层
│   │   │           │   ├── ProviderController.java
│   │   │           │   ├── FutureController.java
│   │   │           │   ├── ModelController.java
│   │   │           │   └── vo/             # 视图对象
│   │   │           ├── service/            # 服务层
│   │   │           │   ├── ProviderService.java
│   │   │           │   ├── FutureService.java
│   │   │           │   ├── ModelService.java
│   │   │           │   └── dto/            # 数据传输对象
│   │   │           ├── dal/                # 数据访问层
│   │   │           │   ├── mapper/         # MyBatis映射器
│   │   │           │   ├── entity/         # 数据对象(DO)
│   │   │           │   └── config/         # 数据库配置
│   │   │           └── common/             # 公共组件
│   │   │               ├── api/            # API客户端
│   │   │               │   └── binance/    # Binance API封装
│   │   │               └── util/           # 工具类
│   │   └── resources/                      # 资源文件
│   │       ├── application.yml            # 应用配置
│   │       ├── mybatis/                   # MyBatis配置
│   │       └── logback-spring.xml         # 日志配置
│   └── test/                              # 测试代码
├── pom.xml                                # Maven依赖
├── Dockerfile                             # Docker配置
└── docker-compose.yml                     # Docker Compose配置
```

## 2. 依赖管理

在pom.xml中添加以下依赖：

- Spring Boot 2.7.x
- MyBatis Plus
- MySQL Connector
- HikariCP
- binance-derivatives-trading-usds-futures 2.0.0
- Lombok
- Swagger/OpenAPI
- JUnit 5

## 3. 数据库设计

### 3.1 数据对象(DO)设计

将原有数据库表映射到Java的DO对象，包括：

- ProviderDO
- FutureDO
- ModelDO
- ConversationDO
- TradeDO
- LlmApiErrorDO

### 3.2 数据访问层设计

使用MyBatis Plus实现数据库交互，包括：

- 基础CRUD操作
- 分页查询
- 自定义SQL查询

## 4. API接口设计

保持与原有API相同的路径和参数，返回相同的数据格式：

### 4.1 Provider API

- GET /api/providers - 获取所有API提供方列表
- POST /api/providers - 添加新的API提供方
- DELETE /api/providers/{providerId} - 删除API提供方
- POST /api/providers/models - 从提供方API获取可用的模型列表

### 4.2 Future API

- GET /api/futures - 获取所有合约配置列表
- POST /api/futures - 添加新的合约配置
- DELETE /api/futures/{futureId} - 删除合约配置

### 4.3 Model API

- GET /api/models - 获取所有交易模型列表
- GET /api/models/{modelId} - 获取单个模型
- POST /api/models - 添加新的交易模型
- DELETE /api/models/{modelId} - 删除交易模型
- GET /api/models/{modelId}/portfolio - 获取模型的投资组合数据
- GET /api/models/{modelId}/portfolio/symbols - 获取模型的持仓合约symbol列表
- GET /api/models/{modelId}/trades - 获取模型的交易历史记录
- GET /api/models/{modelId}/conversations - 获取模型的对话历史记录
- GET /api/models/{modelId}/llm-api-errors - 获取模型的LLM API错误记录
- GET /api/models/{modelId}/prompts - 获取模型的提示词配置
- PUT /api/models/{modelId}/prompts - 更新模型的提示词配置

## 5. 服务层设计

实现业务逻辑，处理DTO和DO之间的转换：

- ProviderService
- FutureService
- ModelService

## 6. 公共组件设计

### 6.1 Binance API客户端封装

使用binance-derivatives-trading-usds-futures 2.0.0库封装Binance API调用，对应原有binance_futures.py功能。

### 6.2 工具类

- 分页工具
- 日期工具
- 字符串工具
- 加密工具

### 6.3 异常处理

统一异常处理机制，返回标准的错误格式。

## 7. Docker配置

### 7.1 Dockerfile

基于JDK 11，使用Spring Boot的内置Tomcat：

```dockerfile
FROM adoptopenjdk:11-jre-hotspot
WORKDIR /app
COPY target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

### 7.2 Docker Compose配置

配置服务启动，包括数据库和应用服务：

```yaml
version: '3.8'
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: aifuturetrade
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
  app:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      - db
    environment:
      SPRING_DATASOURCE_URL: jdbc:mysql://db:3306/aifuturetrade?useSSL=false&serverTimezone=UTC
      SPRING_DATASOURCE_USERNAME: root
      SPRING_DATASOURCE_PASSWORD: root
volumes:
  mysql_data:
```

## 8. 实施步骤

1. 创建项目结构
2. 配置依赖
3. 实现数据库模型和数据访问层
4. 实现Binance API客户端封装
5. 实现服务层
6. 实现控制器层
7. 配置应用和日志
8. 编写测试
9. 配置Docker
10. 测试部署

## 9. 注意事项

1. 保持与原有API相同的路径、参数和返回格式
2. 确保数据类型转换正确
3. 处理好异常情况
4. 确保分页查询等公共能力正常工作
5. 测试所有API端点

这个计划将确保Java后端服务能够与原有的前端无缝集成，同时保持代码结构清晰、职责明确。