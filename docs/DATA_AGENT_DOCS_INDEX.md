# Data Agent 文档索引

## 📚 文档列表

### 1. [业务场景调用链分析](./DATA_AGENT_CALL_CHAIN_ANALYSIS.md)
**详细分析文档，包含：**
- 系统架构概览
- 主场景调用链
- 服务端口构建
- HTTP请求处理流程
- 外部可调用API
- 内部调用链逻辑
- 核心业务场景
- 关键设计模式

**适合：** 深入了解系统架构和调用关系

---

### 2. [调用链可视化图表 (Mermaid)](./DATA_AGENT_CALL_CHAIN_DIAGRAMS.md)
**Mermaid格式的可视化图表，包含：**
- 系统启动流程
- HTTP请求处理流程
- 批量添加Symbol完整流程
- 添加单个流详细流程
- K线消息处理流程
- 连接清理流程
- 定期任务流程
- 错误处理流程
- 服务端口架构
- 数据流图
- 并发处理模型
- 锁机制使用

**适合：** 快速理解系统流程和关系

---

### 3. [调用链时序图 (PlantUML)](./DATA_AGENT_CALL_CHAIN_PLANTUML.md)
**PlantUML格式的时序图，包含：**
- 系统启动流程时序图
- HTTP GET请求处理时序图
- HTTP POST批量添加Symbol时序图
- 添加单个流详细流程时序图
- K线消息处理流程时序图
- 连接清理流程时序图
- 错误处理流程时序图
- 定期任务流程时序图
- 服务端口架构时序图
- 并发处理模型时序图
- 锁机制使用时序图

**适合：** 详细查看方法调用顺序和交互流程

---

### 4. [API快速参考](./DATA_AGENT_API_REFERENCE.md)
**API接口文档，包含：**
- 服务端口说明
- 所有HTTP接口（GET/POST）
- 请求/响应格式
- 调用链说明
- 超时设置
- 频率限制
- 错误处理
- 使用示例

**适合：** 快速查阅API接口和使用方法

---

### 5. [清理资源代码逻辑](./CLEANUP_RESOURCE_LOGIC.md)
**清理资源代码的详细分析，包含：**
- 问题分析
- 修复后的处理逻辑
- 关键设计原则
- 使用示例
- 注意事项

**适合：** 了解资源清理机制

---

## 🎯 快速导航

### 想了解系统架构？
→ 阅读 [业务场景调用链分析](./DATA_AGENT_CALL_CHAIN_ANALYSIS.md)

### 想查看可视化流程图？
→ 阅读 [调用链可视化图表 (Mermaid)](./DATA_AGENT_CALL_CHAIN_DIAGRAMS.md)

### 想查看时序图？
→ 阅读 [调用链时序图 (PlantUML)](./DATA_AGENT_CALL_CHAIN_PLANTUML.md)

### 想查找API接口？
→ 阅读 [API快速参考](./DATA_AGENT_API_REFERENCE.md)

### 想了解资源清理？
→ 阅读 [清理资源代码逻辑](./CLEANUP_RESOURCE_LOGIC.md)

---

## 📋 文档结构

```
docs/
├── DATA_AGENT_DOCS_INDEX.md              # 本文档（索引）
├── DATA_AGENT_CALL_CHAIN_ANALYSIS.md     # 详细分析
├── DATA_AGENT_CALL_CHAIN_DIAGRAMS.md     # 可视化图表 (Mermaid)
├── DATA_AGENT_CALL_CHAIN_PLANTUML.md     # 时序图 (PlantUML)
├── DATA_AGENT_API_REFERENCE.md           # API参考
└── CLEANUP_RESOURCE_LOGIC.md             # 清理逻辑
```

---

## 🔍 关键概念速查

### 服务端口
- **指令服务器**: 端口 9999，处理所有指令请求
- **状态服务器**: 端口 9988，仅处理健康检查

### 核心类
- **DataAgentKlineManager**: 管理所有K线连接和流
- **DataAgentCommandHandler**: 处理指令请求
- **DataAgentStatusHandler**: 处理状态检查

### 关键方法
- **add_stream()**: 添加单个K线流（7个步骤）
- **add_symbol_streams()**: 为symbol添加所有interval的流
- **_handle_kline_message()**: 处理K线消息

### 设计模式
- **多线程HTTP服务器**: 支持并发请求
- **异步操作**: 通过事件循环执行
- **锁机制**: 保护共享资源
- **超时保护**: 避免卡住
- **错误恢复**: 自动清理断开的连接

---

## 📖 阅读建议

1. **新手**: 先看 [API快速参考](./DATA_AGENT_API_REFERENCE.md)，了解基本接口
2. **开发者**: 看 [调用链可视化图表](./DATA_AGENT_CALL_CHAIN_DIAGRAMS.md)，理解流程
3. **架构师**: 看 [业务场景调用链分析](./DATA_AGENT_CALL_CHAIN_ANALYSIS.md)，深入理解设计

---

## 🔗 相关代码文件

- `data/data_agent.py`: 主代码文件
- `tests/test_data_agent_step_by_step.py`: 分步测试
- `tests/test_data_agent.py`: 完整测试
- `tests/test_data_agent_batch_performance.py`: 性能测试

