# JVM 反射访问警告修复

## 问题描述

在 Java 9+ 版本中，MyBatis-Plus 使用反射访问 `java.lang.invoke.SerializedLambda` 的内部字段时会产生警告：

```
WARNING: An illegal reflective access operation has occurred
WARNING: Illegal reflective access by com.baomidou.mybatisplus.core.toolkit.SetAccessibleAction 
         to field java.lang.invoke.SerializedLambda.capturingClass
```

## 解决方案

在 JVM 启动参数中添加 `--add-opens` 参数，允许访问所需的内部 API。

### 修复位置

1. **Dockerfile** (`backend/Dockerfile`)
   ```dockerfile
   ENV JAVA_OPTS="-Xms512m -Xmx1024m -Dserver.port=5002 --add-opens java.base/java.lang.invoke=ALL-UNNAMED"
   ```

2. **Docker Compose** (`docker-compose.yml`)
   ```yaml
   - JAVA_OPTS=${JAVA_OPTS:--Xms512m -Xmx1024m -Dserver.port=5002 --add-opens java.base/java.lang.invoke=ALL-UNNAMED}
   ```

### 参数说明

- `--add-opens java.base/java.lang.invoke=ALL-UNNAMED`
  - 允许所有未命名模块访问 `java.base/java.lang.invoke` 包
  - 这是 Java 9+ 推荐的解决方案，比 `--illegal-access=permit` 更精确和安全

### 其他可选方案

如果上述方案不满足需求，可以考虑：

1. **允许所有非法访问（不推荐，仅用于临时测试）**
   ```bash
   --illegal-access=permit
   ```

2. **升级 MyBatis-Plus 版本**
   - 检查是否有新版本修复了此问题
   - 当前版本：3.5.3.1

3. **使用 Java 8（不推荐）**
   - Java 8 不限制反射访问，但已过时

### 验证

重启应用后，警告应该消失。如果仍有警告，检查：
1. JVM 参数是否正确传递
2. Java 版本是否为 9+
3. MyBatis-Plus 版本是否兼容

## 参考

- [Java 9+ 模块系统](https://openjdk.java.net/projects/jigsaw/)
- [MyBatis-Plus 官方文档](https://baomidou.com/)

