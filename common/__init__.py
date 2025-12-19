"""Common package - 基础服务模块

包含支撑业务的基础服务：
- config: 配置管理
- database: 数据库操作模块包（包含所有 database_* 模块）
- binance_futures: 币安期货客户端
- version: 版本信息

注意：
- 交易相关服务（ai.ai_trader, trading_engine, ai.prompt_defaults）已迁移到 trade 包
- 市场数据服务（market_data, market_streams）已迁移到 market 包
"""

