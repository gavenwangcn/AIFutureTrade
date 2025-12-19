# Binance SDK 升级说明

## 版本升级：2.0.0 → 6.0.0

### 更新内容

1. **依赖版本更新**
   - `binance-derivatives-trading-usds-futures`: `2.0.0` → `6.0.0`
   - Jakarta Validation API 保持不变（`3.0.2`）
   - Hibernate Validator 保持不变（`7.0.5.Final`）

### 兼容性检查

#### ✅ 应该兼容的部分

以下代码在 6.0.0 版本中应该仍然可用：

1. **核心 API 类**
   - `DerivativesTradingUsdsFuturesRestApi`
   - `ClientConfiguration`
   - `SignatureConfiguration`
   - `DerivativesTradingUsdsFuturesRestApiUtil`

2. **使用这些类的文件**
   - `BinanceClient.java`
   - `BinanceFuturesBase.java`
   - `BinanceFuturesClient.java`
   - `BinanceFuturesAccountClient.java`
   - `BinanceFuturesOrderClient.java`

#### ⚠️ 需要注意的部分

1. **API 方法可能变化**
   - 某些方法签名可能已更新
   - 返回值类型可能有所变化
   - 异常处理方式可能不同

2. **配置方式可能变化**
   - `ClientConfiguration` 的配置方式可能有所调整
   - `SignatureConfiguration` 的设置方法可能更新

3. **依赖管理**
   - Binance SDK 6.0.0 可能已经更新了内部依赖版本
   - 如果构建时出现依赖冲突，可能需要调整 Jakarta Validation 的版本

### 测试建议

升级后，请重点测试以下功能：

1. **API 客户端初始化**
   - 检查 `BinanceClient` 和 `BinanceFuturesBase` 的初始化是否正常
   - 验证 HMAC 和 RSA/ED25519 认证方式是否都能正常工作

2. **市场数据获取**
   - 测试 `BinanceFuturesClient` 的价格获取功能
   - 测试 K 线数据获取功能
   - 测试 24 小时统计获取功能

3. **账户操作**
   - 测试 `BinanceFuturesAccountClient` 的账户信息获取
   - 测试账户余额查询

4. **订单操作**
   - 测试 `BinanceFuturesOrderClient` 的市场订单
   - 测试限价订单
   - 测试止损/止盈订单
   - 测试平仓操作

### 如果遇到问题

1. **依赖冲突**
   - 如果出现 `NoClassDefFoundError` 或 `ClassNotFoundException`
   - 检查 Binance SDK 6.0.0 的依赖树：`mvn dependency:tree`
   - 可能需要排除或更新某些传递依赖

2. **API 方法不存在**
   - 如果编译时出现方法不存在的错误
   - 检查 Binance SDK 6.0.0 的 API 文档
   - 可能需要更新方法调用方式

3. **运行时错误**
   - 如果运行时出现异常
   - 检查日志中的详细错误信息
   - 参考 Binance SDK 6.0.0 的更新日志

### 回滚方案

如果升级后出现问题，可以快速回滚：

1. 将 `pom.xml` 中的版本改回 `2.0.0`
2. 重新构建：`mvn clean package`
3. 重新部署服务

### 参考资源

- [Binance Connector Java GitHub](https://github.com/binance/binance-connector-java)
- [Binance API 文档](https://developers.binance.com/docs)
- [Binance SDK 更新日志](https://github.com/binance/binance-connector-java/releases)

