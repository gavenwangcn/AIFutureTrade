# Python 到 Java 迁移状态

## 已完成的工作

### 1. 实体类（Entity）
- ✅ PortfolioDO - 投资组合持仓
- ✅ SettingsDO - 系统设置
- ✅ ModelPromptDO - 模型提示词配置
- ✅ AccountAssetDO - 账户资产
- ✅ AccountValueHistoryDO - 账户价值历史记录
- ✅ MarketTickerDO - 市场Ticker数据（24_market_tickers表）
- ✅ 已有：ModelDO, ProviderDO, FutureDO, TradeDO, ConversationDO, LlmApiErrorDO

### 2. Mapper 接口
- ✅ PortfolioMapper
- ✅ SettingsMapper
- ✅ ModelPromptMapper
- ✅ AccountAssetMapper（已实现 selectAllAccounts 方法）
- ✅ AccountValueHistoryMapper
- ✅ MarketTickerMapper（已实现涨跌幅榜查询方法）
- ✅ 已有：ModelMapper, ProviderMapper, FutureMapper, TradeMapper, ConversationMapper, LlmApiErrorMapper

### 3. Service 接口
- ✅ MarketService - 市场数据服务
- ✅ SettingsService - 系统设置服务
- ✅ AccountService - 账户管理服务
- ✅ 已有：ModelService, ProviderService, FutureService（部分方法需要完善）

### 4. Service 实现类
- ✅ MarketServiceImpl - 市场数据服务实现（已实现涨跌幅榜查询逻辑，从数据库 24_market_tickers 表查询）
- ✅ SettingsServiceImpl - 系统设置服务实现
- ✅ AccountServiceImpl - 账户管理服务实现（已实现账户添加、删除、查询功能）
- ✅ ModelServiceImpl - 已完成所有 TODO 部分（portfolio, trades, conversations, prompts, batch-config, max_positions, leverage, provider, auto-trading, aggregated-portfolio 等）

### 5. Controller
- ✅ MarketController - 市场数据 API
- ✅ SettingsController - 系统设置 API
- ✅ AccountController - 账户管理 API
- ✅ ModelController - 已完成所有 API 端点（包括 batch-config, max_positions, leverage, provider, auto-trading, aggregated-portfolio 等）
- ✅ ProviderController（已有）
- ✅ FutureController（已有）

## 待完成的工作

### 1. Service 实现类
- ✅ MarketServiceImpl - 已实现涨跌幅榜查询逻辑
- ✅ SettingsServiceImpl - 系统设置服务（已完成）
- ✅ AccountServiceImpl - 账户管理服务（已完成）
- ✅ ModelServiceImpl - 已完成所有功能

### 2. Controller
- ✅ MarketController - 市场数据 API（已完成）
- ✅ SettingsController - 系统设置 API（已完成）
- ✅ AccountController - 账户管理 API（已完成）
- ✅ ModelController - 已完成所有 API 端点

### 3. 异步任务类（common/async）
- ✅ LeaderboardAsyncService - 涨跌幅榜同步任务（已创建，使用 @Scheduled 定时执行）
- ✅ 在主应用类中启用 @EnableAsync 和 @EnableScheduling 支持

### 4. 工具类（common/util）
- ✅ 已创建基础工具类：PageRequest, PageResult
- ⏳ 根据需要可继续创建其他工具类（MarketDataUtil, DateTimeUtil, SymbolUtil 等）

### 5. 配置迁移
- ✅ 完善 application.yml 配置（已添加所有缺失的配置项，包括交易配置、市场数据配置、AI决策配置、异步服务配置等）

### 6. DAO 层方法实现
- ⏳ 完善 Mapper XML 文件或使用 MyBatis-Plus 注解实现复杂查询

## 注意事项

1. **不迁移的内容**：
   - `_start_trading_loops_if_needed()` 相关的 AI 买入和卖出交易循环
   - `trading_buy_loop()` 和 `trading_sell_loop()` 函数

2. **需要保持的逻辑**：
   - 所有 API 接口的请求/响应格式
   - 数据库操作逻辑
   - 业务规则和验证逻辑

3. **技术栈**：
   - 使用 Spring Boot
   - 使用 MyBatis-Plus 进行数据库操作
   - 使用 Binance Java SDK（已在 common/api/binance 中实现）
   - 使用 Spring 的 @Async 或 Scheduled 实现异步任务

