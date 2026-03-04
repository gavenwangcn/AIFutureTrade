# AIFutureTrade - AI-Powered Cryptocurrency Futures Trading System

<div align="center">

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Java](https://img.shields.io/badge/Java-17-orange.svg)](https://www.oracle.com/java/)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-green.svg)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.2.0-brightgreen.svg)](https://spring.io/projects/spring-boot)

一个生产级别的AI驱动数字资产交易系统，集成多时间周期技术分析、实时风险管理和智能决策引擎。支持币安期货实时交易、毫秒级订单执行、一键平仓、异步止损等企业级交易能力。采用Java+Python微服务架构，基于LLM的策略生成与优化，完整的交易日志与决策追踪。

[中文](#chinese) | [English](#english)

</div>

---

## <a name="chinese"></a>中文

### 📋 目录

- [概述](#概述)
- [功能](#功能)
- [架构](#架构-1)
- [快速开始](#快速开始-1)
- [配置](#配置-1)
- [API 文档](#api-文档)
- [赞助支持](#赞助支持)
- [界面截图](#界面截图)

### 概述

AIFutureTrade 是面向 Binance 合约的智能自动交易系统，采用微服务与容器化架构，覆盖策略管理、行情处理、风控与交易执行等全链路能力。

### 功能

- **策略与模型**：多模型独立容器运行，动态创建/启动/停止
- **行情与指标**：WebSocket 实时行情，内置多种技术指标
- **交易执行**：低延迟下单与持仓管理，支持止盈止损与风控
- **数据与审计**：交易与持仓全量落库，日志可追溯

### 📊 系统功能全介绍

#### 1. 模型与策略管理

| 功能 | 说明 | 实现位置 |
|------|------|---------|
| **模型CRUD** | 创建、查询、更新、删除交易模型 | Backend API `/api/models` |
| **模型配置** | 设置杠杆、最大持仓、初始资金 | ModelController |
| **自动交易控制** | 独立启用/禁用买入和卖出循环 | Model auto_buy/auto_sell 标志 |
| **风控参数** | 配置止损%、日收益目标、连续亏损限制 | ModelDO 实体 |
| **批量执行** | 配置批量大小、执行间隔、分组执行 | 模型批量配置 |
| **策略关联** | 将多个策略与优先级关联到模型 | ModelStrategyController |
| **策略代码执行** | 执行数据库中的Python策略代码 | StrategyTrader 类 |
| **AI提供商选择** | 选择OpenAI、Claude、DeepSeek、Gemini等 | AiProviderController |
| **自定义提示词** | 为每个模型定义买入/卖出提示词 | ModelPromptDO 表 |

#### 2. 交易执行

| 功能 | 说明 | 实现位置 |
|------|------|---------|
| **买入循环** | 获取涨幅榜、过滤、执行AI决策 | TradingEngine._execute_buy_cycle() |
| **卖出循环** | 监控持仓、执行卖出信号 | TradingEngine._execute_sell_cycle() |
| **市价单** | 执行即时市价单 | BinanceFuturesOrderClient |
| **限价单** | 以自定义价格下限价单 | 订单执行服务 |
| **止损单** | 自动创建止损订单 | AlgoOrderService |
| **止盈单** | 自动创建止盈订单 | AlgoOrderService |
| **平仓** | 一键平仓功能 | BinanceFuturesOrderServiceImpl |
| **数量精度** | 根据价格自动调整数量 | QuantityNormalizer |
| **杠杆管理** | 设置和调整每个持仓的杠杆 | BinanceFuturesOrderClient |
| **对冲模式** | 支持LONG/SHORT持仓模式 | 持仓模式配置 |

#### 3. 市场数据与指标

| 功能 | 说明 | 实现位置 |
|------|------|---------|
| **实时行情流** | WebSocket连接币安行情 | MarketTickerStreamService |
| **K线数据** | 获取历史K线数据（1m-1w） | BinanceFuturesClient |
| **多时间周期** | 支持15m、30m、1h、4h、1d周期 | MarketDataManager |
| **ATR指标** | 平均真实波幅用于波动率计算 | MarketIndexCalculator |
| **ADX指标** | 平均方向指数用于趋势强度 | MarketIndexCalculator |
| **RSI指标** | 相对强弱指数（通过TA-Lib） | TA-Lib集成 |
| **MACD指标** | 移动平均收敛散度 | TA-Lib集成 |
| **布林带** | 布林带用于波动率带状 | TA-Lib集成 |
| **市场波动率指数** | 计算市场范围内的波动率指标 | calculate_market_volatility() |
| **市场趋势指数** | 计算市场范围内的趋势强度 | calculate_market_trend_strength() |
| **价格刷新** | 定期更新所有合约价格 | PriceRefreshService |
| **符号离线检测** | 检测下架或离线的合约 | MarketSymbolOfflineService |

#### 4. 风险管理

| 功能 | 说明 | 实现位置 |
|------|------|---------|
| **头寸规模** | 根据风险%计算头寸大小 | RiskCalculator |
| **最大持仓限制** | 强制执行每个模型的最大持仓数 | Model max_positions 配置 |
| **亏损自动平仓** | 在亏损阈值处自动平仓 | AutoCloseService |
| **连续亏损追踪** | 追踪并限制连续亏损 | TradingEngine |
| **日收益目标** | 监控并强制执行日利润目标 | AccountValuesDailyService |
| **成交量过滤** | 按最小交易量过滤合约 | BaseVolumeFilter |
| **禁止买入时间** | 限制特定时间段的买入订单 | ForbiddenBuyTimeFilter |
| **同合约间隔** | 强制同一合约买入之间的最小间隔 | SameSymbolIntervalFilter |
| **滑点容差** | 配置可接受的滑点百分比 | 交易执行配置 |
| **账户价值追踪** | 监控账户价值随时间的变化 | AccountValueHistoryDO |

#### 5. 前端UI组件

| 功能 | 说明 | 技术栈 |
|------|------|--------|
| **仪表板** | 主交易仪表板与控制按钮 | Vue 3 + Vite |
| **模型管理UI** | 创建、编辑、删除模型 | 模态对话框 |
| **投资组合显示** | 显示当前持仓和盈亏 | 实时更新 |
| **交易历史** | 分页交易列表与详情 | DataTable组件 |
| **K线图表** | 交互式K线图 | KLineChart 10.0.0 |
| **技术指标** | MA、EMA、MACD、KDJ、RSI、ATR叠加 | 图表指标 |
| **市场排行榜** | 涨幅榜和跌幅榜显示 | MarketController |
| **设置模态框** | 配置模型参数 | SettingsController |
| **策略管理器** | 管理策略代码和关联 | StrategyController |
| **买入/卖出日志** | 实时执行日志 | WebSocket流 |
| **交易日志** | 合并的交易历史日志 | TradeLogsWebSocketHandler |
| **微信通知** | 配置微信告警webhook | SettingsController |

#### 6. 数据管理

| 功能 | 说明 | 数据库表 |
|------|------|---------|
| **交易记录** | 完整的交易历史与信号 | trades |
| **持仓追踪** | 当前和历史持仓 | portfolios |
| **策略定义** | 策略代码和元数据 | strategys |
| **模型配置** | 模型设置和参数 | models |
| **账户价值** | 当前账户价值快照 | account_values |
| **账户历史** | 历史账户价值追踪 | account_value_historys |
| **日度汇总** | 日度账户价值汇总 | account_values_daily |
| **策略决策** | AI决策记录和理由 | strategy_decisions |
| **条件订单** | 条件订单追踪 | algo_order |
| **市场行情** | 实时市场数据缓存 | market_tickers |
| **合约配置** | 可交易合约配置 | futures |
| **AI提供商** | API提供商凭证 | providers |
| **对话历史** | AI对话历史 | conversations |

#### 7. 系统集成

| 功能 | 说明 | 集成方式 |
|------|------|---------|
| **币安REST API** | 账户、订单、持仓、行情数据 | BinanceFuturesClient |
| **币安WebSocket** | 实时行情和订单更新 | MarketTickerStreamService |
| **Docker管理** | 动态容器生命周期 | Docker Java API |
| **MySQL数据库** | 持久化数据存储 | MyBatis Plus ORM |
| **JWT认证** | 安全API认证 | JwtTokenProvider |
| **CORS配置** | 跨域请求处理 | CorsConfig |
| **WebSocket服务器** | 实时前端更新 | WebSocketConfig |
| **REST API网关** | 集中式API路由 | Spring Boot |
| **服务发现** | 容器DNS解析 | Docker桥接网络 |
| **健康检查** | 服务健康监控 | Spring Boot Actuator |

#### 8. 监控与告警

| 功能 | 说明 | 实现位置 |
|------|------|---------|
| **容器健康** | 监控async-service容器状态 | TradeMonitorService |
| **行情流超时** | 检测WebSocket连接失败 | ConnectionMonitor |
| **自动重启** | 自动重启失败的容器 | ContainerRestartService |
| **微信告警** | 发送通知到微信群 | WeChatNotificationService |
| **服务日志** | 所有服务的集中式日志 | SLF4J + Logback |
| **交易执行日志** | 详细的交易执行追踪 | TradeLogsWebSocketHandler |
| **模型执行日志** | 每个模型的执行日志 | ModelLogsWebSocketHandler |
| **错误追踪** | SDK错误记录和报告 | ErrorHandler |
| **性能指标** | 追踪执行时间和吞吐量 | MetricsCollector |

#### 9. 高级功能

| 功能 | 说明 | 详情 |
|------|------|------|
| **多时间周期分析** | 1h、4h、1d的ADX计算 | _calculate_symbol_adx() |
| **市场状态聚合** | 合并波动率和趋势指标 | calculate_comprehensive_market_state() |
| **批量处理** | 并发AI决策处理 | BatchDecisionProcessor |
| **策略优先级** | 按优先级执行策略 | ModelStrategyDO priority字段 |
| **多策略合并** | 合并来自多个策略的决策 | StrategyTrader |
| **对话历史** | 追踪AI决策推理 | ConversationDO 表 |
| **Token使用追踪** | 监控LLM API Token消耗 | AiTrader |
| **降级处理** | API失败时的优雅降级 | ErrorHandler |
| **数据规范化** | 规范化价格和数量 | DataNormalizer |
| **时区支持** | UTC+8时区处理 | TimeZoneConfig |

### 架构

- **前端**：Vue 3 + KLineChart 实时可视化
- **后端**：Spring Boot 业务与模型管理
- **交易服务**：Python 交易引擎与指标计算
- **异步服务**：行情流处理与定时任务
- **币安服务**：Binance API 调用与限流

#### 系统架构图

```mermaid
graph TB
    subgraph "Client Layer"
        USER[User Browser]
    end

    subgraph "Frontend Layer"
        FE[Vue 3 Frontend<br/>Port 3000<br/>Vite + KLineChart]
    end

    subgraph "API Gateway Layer"
        BE[Backend Service<br/>Java Spring Boot<br/>Port 5002<br/>User/Model Management]
    end

    subgraph "Core Services Layer"
        BS[Binance Service<br/>Java + Undertow<br/>Port 5004<br/>Market Data API]
        AS[Async Service<br/>Java Spring Boot<br/>Port 5003<br/>WebSocket Stream]
        TS[Trade Service<br/>Python Flask<br/>Port 5000<br/>Trading Engine]
    end

    subgraph "Dynamic Model Layer"
        MB1[Buy Model 1<br/>Python Container]
        MB2[Buy Model 2<br/>Python Container]
        MS1[Sell Model 1<br/>Python Container]
        MS2[Sell Model 2<br/>Python Container]
    end

    subgraph "External Services"
        BINANCE[Binance API<br/>Futures Market<br/>WebSocket + REST]
        DB[(MySQL 8.0<br/>Port 32123<br/>Trade Data)]
    end

    subgraph "Docker Infrastructure"
        DOCKER[Docker Engine<br/>Container Management]
    end

    USER -->|HTTPS| FE
    FE -->|HTTP/WebSocket| BE
    BE -->|REST API| TS
    BE -->|REST API| BS
    BE -->|REST API| AS
    BE -->|Docker API| DOCKER
    BE -->|JDBC| DB

    DOCKER -->|Manage| MB1
    DOCKER -->|Manage| MB2
    DOCKER -->|Manage| MS1
    DOCKER -->|Manage| MS2

    BS -->|HTTPS| BINANCE
    AS -->|WebSocket| BINANCE
    AS -->|JDBC| DB
    TS -->|HTTPS| BINANCE
    TS -->|JDBC| DB

    MB1 -->|Trade Logic| TS
    MB2 -->|Trade Logic| TS
    MS1 -->|Trade Logic| TS
    MS2 -->|Trade Logic| TS
```

#### 网络架构

```mermaid
graph LR
    subgraph "Public Network"
        INTERNET[Internet]
    end

    subgraph "Docker Bridge Network: aifuturetrade-network"
        subgraph "Frontend Container"
            FE[frontend:3000]
        end

        subgraph "Backend Container"
            BE[backend:5002]
        end

        subgraph "Service Containers"
            BS[binance-service:5004]
            AS[async-service:5003]
            TS[trade:5000]
        end

        subgraph "Model Containers"
            MB["buy-<modelId>"]
            MS["sell-<modelId>"]
        end

        subgraph "Database Container"
            DB[mysql:32123]
        end
    end

    INTERNET -->|Port 3000| FE
    INTERNET -->|Port 5002| BE

    FE -.->|Internal DNS| BE
    BE -.->|Internal DNS| BS
    BE -.->|Internal DNS| AS
    BE -.->|Internal DNS| TS
    BE -.->|Internal DNS| DB

    BS -.->|Internal DNS| DB
    AS -.->|Internal DNS| DB
    TS -.->|Internal DNS| DB

    MB -.->|Internal DNS| TS
    MS -.->|Internal DNS| TS
```

### 快速开始

1. 克隆仓库并进入目录  
   `git clone https://github.com/gavenwangcn/AIFutureTrade.git`

2. 准备环境变量  
   复制 `.env.example` 为 `.env` 并补充配置（重点是 Binance API 与 MySQL）

3. 启动 MySQL（必须先启动）  
   `docker-compose -f docker-compose-mysql.yml up -d`

4. 启动全部服务  
   `docker-compose up -d --build --scale model-buy=0 --scale model-sell=0`

### 配置

核心配置均在 `.env`，包含数据库连接、Binance API 密钥、服务端口、异步任务与风控参数。  
后端的详细配置位于 `backend/src/main/resources/application.yml`。

### API 文档

- **Backend**: http://localhost:5002/swagger-ui.html  
- **Binance Service**: http://localhost:5004/swagger-ui.html  
- **Trade Service**: http://localhost:5000/api/docs

### 部署

#### 开发环境

- 适合本地调试与功能验证，可用 Docker 统一启动
- 建议先启动 MySQL，再启动其余服务

#### 生产环境

- 建议使用独立数据库与反向代理（Nginx/Traefik）
- 开启 HTTPS、日志与监控、资源限制、备份策略

#### 生产环境清单

- 独立 MySQL / 云数据库，开启备份与只读账号
- 反向代理 + HTTPS，配置安全头与限流
- 日志与监控（Prometheus/Grafana/ELK）
- Docker 资源限制与自动重启策略
- 秘钥与环境变量通过安全方式注入（避免硬编码）
- 时区统一（Asia/Shanghai）与系统时间同步
- 定期清理与归档历史数据

#### Docker 部署

```
docker-compose -f docker-compose-mysql.yml up -d
docker-compose up -d --build --scale model-buy=0 --scale model-sell=0
```

### 开发

- Java 服务：`mvn clean package -DskipTests`
- Python 交易服务：`pip install -r requirements.txt`，`python -m trade.app`
- 前端：`npm install`，`npm run dev`

### 监控与日志

- 统一查看容器日志：`docker-compose logs -f <service>`
- 关键服务健康检查：
  - `http://localhost:5002/actuator/health`
  - `http://localhost:5000/health`

### 安全

- Binance API 与数据库账号请勿提交到仓库
- 生产环境请替换默认口令与密钥
- JWT、CORS 与网络访问建议按最小权限配置

### 性能优化

- Java 服务开启 G1GC 与合理的堆内存参数
- 异步服务与行情刷新任务支持可配置调度
- 数据访问建议配合缓存/限流策略

### 故障排查

- 先确认 MySQL 容器健康
- 检查端口占用与服务日志
- SDK 依赖构建失败时，先构建 Binance SDK 子模块

### 贡献指南

请查看 `CONTRIBUTING.md`。

### 许可证

本项目基于 MIT License，详见 `LICENSE`。

### 💖 赞助支持

如果这个项目对您有帮助，欢迎通过以下方式支持项目的持续开发与维护：

<div align="center">

<table>
  <tr>
    <td align="center">
      <img src="img/contact.jpg" alt="联系人" width="50%" />
    </td>
    <td align="center">
      <img src="img/receive.jpg" alt="赞助支持" width="50%" />
    </td>
  </tr>
</table>

**感谢您的支持！您的赞助将用于：**
- 🚀 持续优化交易策略与算法
- 🔧 修复 Bug 与改进用户体验
- 📚 完善文档与教程
- 💡 开发新功能与特性

</div>

### 🖼️ 界面截图

**K 线与指标分析**  
![K线图](img/Attached_image.png)  
交互式 K 线图，支持 MA/EMA、MACD、KDJ、RSI、ATR 等指标叠加分析。

**策略管理**  
![策略管理](img/Attached2_image.png)  
集中管理策略列表、状态与快捷操作（编辑/启动等）。

**模型级买入执行日志**  
![买入日志](img/Attached3_image.png)  
提供模型实时执行日志，便于排障与运行审计。

**策略绩效与交易列表**  
![策略绩效](img/Attached4_image.png)  
展示策略收益走势与近期交易明细，便于复盘与跟踪执行结果。

**行情总览与涨跌排行**  
![行情总览](img/Attached5_image.png)  
展示 USDS-M 行情总览、涨跌幅排行以及左侧快速合约导航。

## <a name="english"></a>English

### 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
  - [System Architecture](#system-architecture-diagram)
  - [Network Architecture](#network-architecture)
  - [Database Schema](#database-schema)
  - [Container Orchestration](#container-orchestration)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Deployment](#deployment)
  - [Development Environment](#development-environment)
  - [Production Environment](#production-environment)
  - [Docker Deployment](#docker-deployment)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Monitoring & Logging](#monitoring--logging)
- [Security](#security)
- [Performance Optimization](#performance-optimization)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Sponsorship Support](#sponsorship-support)

### 🎯 Overview

AIFutureTrade is a comprehensive automated trading system designed for Binance Futures markets. It leverages AI-driven strategies, real-time market data processing, and a scalable microservices architecture to execute trades efficiently and manage risk effectively.

**Key Highlights:**
- 🤖 AI-powered trading strategies with dynamic model management
- 📊 Real-time market data streaming via WebSocket
- 🔄 Microservices architecture for scalability and maintainability
- 🐳 Fully containerized with Docker for easy deployment
- 📈 Interactive web interface with real-time K-line charts
- ⚡ High-performance async I/O for market data processing
- 🔒 Secure API authentication and data encryption
- 📉 Advanced risk management and position control

### ✨ Features

#### Trading Features
- **AI-Driven Strategies**: Dynamic buy/sell models with independent container execution
- **Risk Management**: Position sizing, stop-loss, and take-profit automation
- **Multi-Symbol Support**: Trade multiple futures contracts simultaneously
- **Real-time Execution**: Low-latency order placement and management
- **Backtesting**: Historical data analysis and strategy validation
- **Paper Trading**: Test strategies without real money

#### Data Processing
- **WebSocket Streaming**: Real-time market ticker data from Binance
- **Historical Data**: K-line data storage and analysis
- **Technical Indicators**: Built-in TA-Lib integration (RSI, MACD, Bollinger Bands, etc.)
- **Data Persistence**: MySQL database for trade history and positions
- **Data Caching**: Redis for high-performance data access

#### System Features
- **Microservices Architecture**: Independent, scalable services
- **Dynamic Container Management**: Auto-scaling trading model containers
- **Health Monitoring**: Service status tracking and auto-restart
- **RESTful APIs**: Comprehensive API endpoints with Swagger documentation
- **WebSocket Support**: Real-time data push to frontend
- **Logging & Monitoring**: Centralized logging with ELK stack support

### 📊 System Capabilities Overview

#### 1. Model & Strategy Management

| Feature | Description | Implementation |
|---------|-------------|-----------------|
| **Model CRUD** | Create, read, update, delete trading models | Backend API `/api/models` |
| **Model Configuration** | Set leverage, max positions, initial capital | ModelController |
| **Auto-Trading Control** | Enable/disable buy and sell cycles independently | Model auto_buy/auto_sell flags |
| **Risk Parameters** | Configure stop-loss %, daily target, loss limits | ModelDO entity |
| **Batch Execution** | Configure batch size, interval, group execution | Batch settings in model config |
| **Strategy Linking** | Associate multiple strategies with priority | ModelStrategyController |
| **Strategy Code Execution** | Execute Python strategy code from database | StrategyTrader class |
| **AI Provider Selection** | Choose between OpenAI, Claude, DeepSeek, Gemini | AiProviderController |
| **Custom Prompts** | Define buy/sell prompts per model | ModelPromptDO table |

#### 2. Trading Execution

| Feature | Description | Implementation |
|---------|-------------|-----------------|
| **Buy Cycle** | Fetch top gainers, filter, execute AI decisions | TradingEngine._execute_buy_cycle() |
| **Sell Cycle** | Monitor positions, execute sell signals | TradingEngine._execute_sell_cycle() |
| **Market Orders** | Execute immediate market orders | BinanceFuturesOrderClient |
| **Limit Orders** | Place limit orders with custom prices | Order execution service |
| **Stop-Loss Orders** | Automatic stop-loss order creation | AlgoOrderService |
| **Take-Profit Orders** | Automatic take-profit order creation | AlgoOrderService |
| **Position Closing** | One-click position close functionality | BinanceFuturesOrderServiceImpl |
| **Quantity Precision** | Auto-adjust quantity based on price | QuantityNormalizer |
| **Leverage Management** | Set and adjust leverage per position | BinanceFuturesOrderClient |
| **Hedge Mode Support** | Support for LONG/SHORT position modes | Position mode configuration |

#### 3. Market Data & Indicators

| Feature | Description | Implementation |
|---------|-------------|-----------------|
| **Real-time Ticker Stream** | WebSocket connection to Binance tickers | MarketTickerStreamService |
| **K-line Data Retrieval** | Fetch historical K-line data (1m-1w) | BinanceFuturesClient |
| **Multi-Timeframe Support** | Support 15m, 30m, 1h, 4h, 1d timeframes | MarketDataManager |
| **ATR Calculation** | Average True Range for volatility | MarketIndexCalculator |
| **ADX Calculation** | Average Directional Index for trend strength | MarketIndexCalculator |
| **RSI Indicator** | Relative Strength Index via TA-Lib | TA-Lib integration |
| **MACD Indicator** | Moving Average Convergence Divergence | TA-Lib integration |
| **Bollinger Bands** | Bollinger Bands for volatility bands | TA-Lib integration |
| **Market Volatility Index** | Calculate market-wide volatility metrics | calculate_market_volatility() |
| **Market Trend Index** | Calculate market-wide trend strength | calculate_market_trend_strength() |
| **Price Refresh** | Periodic price updates for all symbols | PriceRefreshService |
| **Symbol Offline Detection** | Detect delisted or offline symbols | MarketSymbolOfflineService |

#### 4. Risk Management

| Feature | Description | Implementation |
|---------|-------------|-----------------|
| **Position Sizing** | Calculate position size based on risk % | RiskCalculator |
| **Max Position Limit** | Enforce maximum position count per model | Model max_positions config |
| **Auto-Close on Loss** | Automatically close positions at loss threshold | AutoCloseService |
| **Consecutive Loss Tracking** | Track and limit consecutive losses | TradingEngine |
| **Daily Return Target** | Monitor and enforce daily profit targets | AccountValuesDailyService |
| **Volume Filtering** | Filter symbols by minimum trading volume | BaseVolumeFilter |
| **Forbidden Buy Time** | Restrict buy orders during specific hours | ForbiddenBuyTimeFilter |
| **Same Symbol Interval** | Enforce minimum interval between same symbol buys | SameSymbolIntervalFilter |
| **Slippage Tolerance** | Configure acceptable slippage percentage | Trade execution config |
| **Account Value Tracking** | Monitor account value changes over time | AccountValueHistoryDO |

#### 5. Frontend UI Components

| Feature | Description | Technology |
|---------|-------------|------------|
| **Dashboard** | Main trading dashboard with controls | Vue 3 + Vite |
| **Model Management UI** | Create, edit, delete models | Modal dialogs |
| **Portfolio Display** | Show current positions and P&L | Real-time updates |
| **Trade History** | Paginated trade list with details | DataTable component |
| **K-Line Chart** | Interactive candlestick charts | KLineChart 10.0.0 |
| **Technical Indicators** | MA, EMA, MACD, KDJ, RSI, ATR overlays | Chart indicators |
| **Market Leaderboard** | Top gainers/losers display | MarketController |
| **Settings Modal** | Configure model parameters | SettingsController |
| **Strategy Manager** | Manage strategy code and linking | StrategyController |
| **Buy/Sell Logs** | Real-time execution logs | WebSocket streaming |
| **Trade Logs** | Consolidated trade history logs | TradeLogsWebSocketHandler |
| **WeChat Notifications** | Configure WeChat alert webhooks | SettingsController |

#### 6. Data Management

| Feature | Description | Database Table |
|---------|-------------|-----------------|
| **Trade Records** | Complete trade history with signals | trades |
| **Position Tracking** | Current and historical positions | portfolios |
| **Strategy Definitions** | Strategy code and metadata | strategys |
| **Model Configuration** | Model settings and parameters | models |
| **Account Values** | Current account value snapshots | account_values |
| **Account History** | Historical account value tracking | account_value_historys |
| **Daily Aggregation** | Daily account value summaries | account_values_daily |
| **Strategy Decisions** | AI decision records and justification | strategy_decisions |
| **Algo Orders** | Conditional order tracking | algo_order |
| **Market Tickers** | Real-time market data cache | market_tickers |
| **Futures Config** | Tradable contracts configuration | futures |
| **AI Providers** | API provider credentials | providers |
| **Conversations** | AI conversation history | conversations |

#### 7. System Integration

| Feature | Description | Integration |
|---------|-------------|------------|
| **Binance REST API** | Account, orders, positions, market data | BinanceFuturesClient |
| **Binance WebSocket** | Real-time ticker and order updates | MarketTickerStreamService |
| **Docker Management** | Dynamic container lifecycle | Docker Java API |
| **MySQL Database** | Persistent data storage | MyBatis Plus ORM |
| **JWT Authentication** | Secure API authentication | JwtTokenProvider |
| **CORS Configuration** | Cross-origin request handling | CorsConfig |
| **WebSocket Server** | Real-time frontend updates | WebSocketConfig |
| **REST API Gateway** | Centralized API routing | Spring Boot |
| **Service Discovery** | Container DNS resolution | Docker bridge network |
| **Health Checks** | Service health monitoring | Spring Boot Actuator |

#### 8. Monitoring & Alerting

| Feature | Description | Implementation |
|---------|-------------|-----------------|
| **Container Health** | Monitor async-service container status | TradeMonitorService |
| **Ticker Stream Timeout** | Detect WebSocket connection failures | ConnectionMonitor |
| **Auto-Restart** | Automatically restart failed containers | ContainerRestartService |
| **WeChat Alerts** | Send notifications to WeChat groups | WeChatNotificationService |
| **Service Logs** | Centralized logging for all services | SLF4J + Logback |
| **Trade Execution Logs** | Detailed trade execution tracking | TradeLogsWebSocketHandler |
| **Model Execution Logs** | Per-model execution logs | ModelLogsWebSocketHandler |
| **Error Tracking** | SDK error recording and reporting | ErrorHandler |
| **Performance Metrics** | Track execution time and throughput | MetricsCollector |

#### 9. Advanced Features

| Feature | Description | Details |
|---------|-------------|---------|
| **Multi-Timeframe Analysis** | ADX calculation for 1h, 4h, 1d | _calculate_symbol_adx() |
| **Market State Aggregation** | Combine volatility and trend metrics | calculate_comprehensive_market_state() |
| **Batch Processing** | Concurrent AI decision processing | BatchDecisionProcessor |
| **Strategy Priority** | Execute strategies in priority order | ModelStrategyDO priority field |
| **Multi-Strategy Merging** | Combine decisions from multiple strategies | StrategyTrader |
| **Conversation History** | Track AI decision reasoning | ConversationDO table |
| **Token Usage Tracking** | Monitor LLM API token consumption | AiTrader |
| **Fallback Handling** | Graceful degradation on API failures | ErrorHandler |
| **Data Normalization** | Normalize prices and quantities | DataNormalizer |
| **Time Zone Support** | UTC+8 time zone handling | TimeZoneConfig |

### 🖼️ UI Screenshots

**Market Overview & Top Movers**  
![Market Overview](img/Attached_image.png)  
Shows the USDS-M market overview, top movers, and a quick symbol navigation list on the left.

**Strategy Performance & Trade List**  
![Strategy Performance](img/Attached2_image.png)  
Shows strategy performance trends and recent trade details for review and tracking.

**Buy Execution Logs (Model Level)**  
![Buy Logs](img/Attached3_image.png)  
Provides real-time model execution logs for troubleshooting and operational auditing.

**Strategy Management**  
![Strategy Management](img/Attached4_image.png)  
Centralized strategy list with status and quick actions (edit/start).

**K-Line Chart with Indicators**  
![K-Line Chart](img/Attached5_image.png)  
Interactive candlestick chart with MA/EMA, MACD, KDJ, RSI, and ATR overlays.

### 🏗️ Architecture

#### System Architecture Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        USER[User Browser]
    end

    subgraph "Frontend Layer"
        FE[Vue 3 Frontend<br/>Port 3000<br/>Vite + KLineChart]
    end

    subgraph "API Gateway Layer"
        BE[Backend Service<br/>Java Spring Boot<br/>Port 5002<br/>User/Model Management]
    end

    subgraph "Core Services Layer"
        BS[Binance Service<br/>Java + Undertow<br/>Port 5004<br/>Market Data API]
        AS[Async Service<br/>Java Spring Boot<br/>Port 5003<br/>WebSocket Stream]
        TS[Trade Service<br/>Python Flask<br/>Port 5000<br/>Trading Engine]
    end

    subgraph "Dynamic Model Layer"
        MB1[Buy Model 1<br/>Python Container]
        MB2[Buy Model 2<br/>Python Container]
        MS1[Sell Model 1<br/>Python Container]
        MS2[Sell Model 2<br/>Python Container]
    end

    subgraph "External Services"
        BINANCE[Binance API<br/>Futures Market<br/>WebSocket + REST]
        DB[(MySQL 8.0<br/>Port 32123<br/>Trade Data)]
    end

    subgraph "Docker Infrastructure"
        DOCKER[Docker Engine<br/>Container Management]
    end

    USER -->|HTTPS| FE
    FE -->|HTTP/WebSocket| BE
    BE -->|REST API| TS
    BE -->|REST API| BS
    BE -->|REST API| AS
    BE -->|Docker API| DOCKER
    BE -->|JDBC| DB

    DOCKER -->|Manage| MB1
    DOCKER -->|Manage| MB2
    DOCKER -->|Manage| MS1
    DOCKER -->|Manage| MS2

    BS -->|HTTPS| BINANCE
    AS -->|WebSocket| BINANCE
    AS -->|JDBC| DB
    TS -->|HTTPS| BINANCE
    TS -->|JDBC| DB

    MB1 -->|Trade Logic| TS
    MB2 -->|Trade Logic| TS
    MS1 -->|Trade Logic| TS
    MS2 -->|Trade Logic| TS

    style USER fill:#e1f5ff
    style FE fill:#42b983
    style BE fill:#ff6b6b
    style BS fill:#4ecdc4
    style AS fill:#95e1d3
    style TS fill:#f38181
    style BINANCE fill:#ffd93d
    style DB fill:#6c5ce7
    style DOCKER fill:#2496ed
```

#### Network Architecture

```mermaid
graph LR
    subgraph "Public Network"
        INTERNET[Internet]
    end

    subgraph "Docker Bridge Network: aifuturetrade-network"
        subgraph "Frontend Container"
            FE[frontend:3000]
        end

        subgraph "Backend Container"
            BE[backend:5002]
        end

        subgraph "Service Containers"
            BS[binance-service:5004]
            AS[async-service:5003]
            TS[trade:5000]
        end

        subgraph "Model Containers"
            MB["buy-<modelId>"]
            MS["sell-<modelId>"]
        end

        subgraph "Database Container"
            DB[mysql:32123]
        end
    end

    INTERNET -->|Port 3000| FE
    INTERNET -->|Port 5002| BE

    FE -.->|Internal DNS| BE
    BE -.->|Internal DNS| BS
    BE -.->|Internal DNS| AS
    BE -.->|Internal DNS| TS
    BE -.->|Internal DNS| DB

    BS -.->|Internal DNS| DB
    AS -.->|Internal DNS| DB
    TS -.->|Internal DNS| DB

    MB -.->|Internal DNS| TS
    MS -.->|Internal DNS| TS

    style INTERNET fill:#ffd93d
    style FE fill:#42b983
    style BE fill:#ff6b6b
```

#### Database Schema

```mermaid
erDiagram
    USERS ||--o{ MODELS : creates
    USERS ||--o{ TRADES : executes
    MODELS ||--o{ POSITIONS : manages
    MODELS ||--o{ TRADES : generates
    POSITIONS ||--o{ TRADES : affects

    USERS {
        int id PK
        string username
        string password_hash
        string email
        decimal initial_capital
        decimal current_balance
        timestamp created_at
    }

    MODELS {
        int id PK
        int user_id FK
        string model_name
        string model_type
        string strategy_params
        string status
        timestamp created_at
    }

    POSITIONS {
        int id PK
        int model_id FK
        string symbol
        string position_side
        decimal position_amt
        decimal entry_price
        decimal unrealized_pnl
        timestamp open_time
    }

    TRADES {
        int id PK
        int model_id FK
        int user_id FK
        string symbol
        string side
        decimal quantity
        decimal price
        decimal realized_pnl
        timestamp trade_time
    }

    FUTURES {
        int id PK
        string symbol
        decimal leverage
        string margin_type
        timestamp updated_at
    }

    MARKET_TICKERS {
        int id PK
        string symbol
        decimal last_price
        decimal volume_24h
        decimal price_change_percent
        timestamp update_time
    }
```

#### Container Orchestration

```mermaid
graph TB
    subgraph "Docker Compose Orchestration"
        DC[docker-compose.yml]
        DCM[docker-compose-mysql.yml]
    end

    subgraph "Static Containers (Always Running)"
        MYSQL[MySQL Database]
        BACKEND[Backend Service]
        BINANCE[Binance Service]
        ASYNC[Async Service]
        TRADE[Trade Service]
        FRONTEND[Frontend Service]
    end

    subgraph "Dynamic Containers (On-Demand)"
        MB[Model Buy Containers<br/>Created by Backend API]
        MS[Model Sell Containers<br/>Created by Backend API]
    end

    DC -->|Manages| BACKEND
    DC -->|Manages| BINANCE
    DC -->|Manages| ASYNC
    DC -->|Manages| TRADE
    DC -->|Manages| FRONTEND
    DCM -->|Manages| MYSQL

    BACKEND -->|Docker API| MB
    BACKEND -->|Docker API| MS

    style DC fill:#2496ed
    style DCM fill:#2496ed
    style MYSQL fill:#6c5ce7
    style MB fill:#ff9ff3
    style MS fill:#ff9ff3
```

#### Service Responsibilities

| Service | Port | Technology | Responsibility | Scalability |
|---------|------|------------|----------------|-------------|
| **Frontend** | 3000 | Vue 3 + Vite | User interface, real-time charts, WebSocket client | Horizontal |
| **Backend** | 5002 | Java 17 + Spring Boot | Main API, user/model management, Docker orchestration | Horizontal |
| **Binance Service** | 5004 | Java 17 + Undertow | High-performance Binance API proxy, rate limiting | Horizontal |
| **Async Service** | 5003 | Java 17 + Spring Boot | WebSocket streaming, scheduled tasks, data sync | Vertical |
| **Trade Service** | 5000 | Python 3 + Flask | Trading logic, strategy execution, risk management | Horizontal |
| **Model Containers** | Dynamic | Python 3 | Independent buy/sell model execution | Auto-scaling |
| **MySQL** | 32123 | MySQL 8.0 | Persistent data storage | Master-Slave |

#### Data Flow Sequence

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Docker
    participant Model
    participant Trade
    participant Binance
    participant DB

    User->>Frontend: Create Trading Model
    Frontend->>Backend: POST /api/models
    Backend->>DB: Save Model Config
    Backend->>Docker: Create Container (buy-{modelId})
    Docker-->>Backend: Container Created
    Backend->>Model: Start Model Process
    Model->>Trade: Initialize Strategy
    Trade->>Binance: Fetch Market Data
    Binance-->>Trade: K-line Data
    Trade->>Trade: Calculate Indicators (RSI, MACD)
    Trade->>Trade: Generate Signal
    Trade->>Binance: Place Order (LIMIT/MARKET)
    Binance-->>Trade: Order Confirmation
    Trade->>DB: Save Trade Record
    Trade->>DB: Update Position
    Backend->>Frontend: WebSocket Push (Status Update)
    Frontend-->>User: Display Results
```

#### Real-time Data Flow

```mermaid
sequenceDiagram
    participant Binance
    participant AsyncService
    participant DB
    participant Backend
    participant Frontend
    participant User

    Binance->>AsyncService: WebSocket Stream (Ticker Data)
    AsyncService->>DB: Update 24_market_tickers
    AsyncService->>Backend: Notify Data Update
    Backend->>Frontend: WebSocket Push (Price Update)
    Frontend-->>User: Update K-line Chart

    Note over AsyncService: Every 5 minutes
    AsyncService->>DB: Refresh Price Data

    Note over AsyncService: Every 30 minutes
    AsyncService->>DB: Clean Expired Data
```

### 🛠️ Tech Stack

#### Backend Services
- **Java 17**: Modern Java features (Records, Pattern Matching, Sealed Classes)
- **Spring Boot 3.2.0**: Microservices framework with auto-configuration
- **MyBatis Plus 3.5.5**: Enhanced ORM with code generator
- **Undertow 2.3.10**: High-performance async I/O server (NIO)
- **Docker Java API 3.3.4**: Dynamic container lifecycle management
- **Lombok**: Reduce boilerplate code
- **Swagger/OpenAPI 3.0**: API documentation

#### Trading Engine
- **Python 3.9+**: Core trading logic and strategy execution
- **Flask 2.3.0**: Lightweight RESTful API framework
- **Gunicorn 21.2.0**: WSGI HTTP server
- **Eventlet 0.33.3**: Concurrent networking library
- **TA-Lib 0.4.28**: Technical analysis (150+ indicators)
- **Pandas 2.1.0**: Data manipulation and analysis
- **NumPy 1.25.0**: Numerical computing
- **python-binance 1.0.19**: Binance API wrapper

#### Frontend
- **Vue 3.3.4**: Composition API with `<script setup>`
- **Vite 4.4.9**: Fast build tool with HMR
- **KLineChart (Latest)**: Professional candlestick charting library
- **Axios 1.5.0**: Promise-based HTTP client
- **Pinia 2.1.6**: State management
- **Vue Router 4.2.4**: Client-side routing
- **Element Plus 2.3.14**: UI component library

#### Infrastructure
- **MySQL 8.0.35**: ACID-compliant relational database
- **Docker 24.0+**: Container runtime
- **Docker Compose 2.20+**: Multi-container orchestration
- **Nginx** (Optional): Reverse proxy and load balancer
- **Redis** (Optional): Caching and session storage

#### Development Tools
- **Maven 3.9+**: Java dependency management
- **npm/pnpm**: JavaScript package management
- **Git**: Version control
- **IntelliJ IDEA / VS Code**: IDE

### 🚀 Quick Start

#### Prerequisites

```bash
# Required
- Docker 20.10+ and Docker Compose 2.0+
- Git 2.30+
- 4GB+ RAM available for containers
- 10GB+ disk space

# Optional (for local development)
- Java 17 (OpenJDK or Oracle JDK)
- Python 3.9+
- Node.js 18+ and npm 9+
- Maven 3.9+
```

#### Installation

1. **Clone the repository**
```bash
git clone https://github.com/gavenwangcn/AIFutureTrade.git
cd AIFutureTrade
```

2. **Configure environment variables**
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
# IMPORTANT: Set your Binance API credentials
nano .env  # or use your preferred editor
```

3. **Start MySQL database (Required First)**
```bash
# Start MySQL container
docker-compose -f docker-compose-mysql.yml up -d

# Wait for MySQL to be ready (about 30 seconds)
docker-compose -f docker-compose-mysql.yml logs -f mysql

# Verify MySQL is running
docker-compose -f docker-compose-mysql.yml ps
```

4. **Build and start all services**
```bash
# Option 1: Use the provided script (Recommended)
chmod +x scripts/docker-compose-up.sh
./scripts/docker-compose-up.sh --build

# Option 2: Manual start (model containers won't auto-start)
docker-compose up -d --build --scale model-buy=0 --scale model-sell=0

# Option 3: Build specific services
docker-compose build backend frontend trade
docker-compose up -d backend frontend trade
```

5. **Verify services are running**
```bash
# Check all containers status
docker-compose ps

# Check logs
docker-compose logs -f backend
docker-compose logs -f trade
docker-compose logs -f async-service

# Health check
curl http://localhost:5002/actuator/health
curl http://localhost:5000/health
```

6. **Access the application**
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:5002
- **Swagger UI (Backend)**: http://localhost:5002/swagger-ui.html
- **Swagger UI (Binance Service)**: http://localhost:5004/swagger-ui.html
- **Async Service Status**: http://localhost:5003/api/async/status

### 📦 Deployment

#### Development Environment

**Local Development without Docker:**

1. **Start MySQL**
```bash
docker-compose -f docker-compose-mysql.yml up -d
```

2. **Backend Service**
```bash
cd backend
mvn clean package -DskipTests
java -jar target/backend-1.0.0.jar
```

3. **Trade Service**
```bash
cd trade
pip install -r requirements.txt
python -m trade.app
```

4. **Frontend**
```bash
cd frontend
npm install
npm run dev
```

#### Production Environment

**Production Deployment Checklist:**

- [ ] Use production-grade MySQL (RDS, Cloud SQL, etc.)
- [ ] Configure reverse proxy (Nginx/Traefik)
- [ ] Enable HTTPS with SSL certificates
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure centralized logging (ELK Stack)
- [ ] Enable database backups
- [ ] Set resource limits for containers
- [ ] Use secrets management (Vault, AWS Secrets Manager)
- [ ] Configure firewall rules
- [ ] Set up CI/CD pipeline

**Production Docker Compose:**

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    image: aifuturetrade/backend:latest
    restart: always
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - JAVA_OPTS=-Xms1g -Xmx2g -XX:+UseG1GC
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5002/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # ... other services
```

**Deploy to Production:**

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Push to registry
docker-compose -f docker-compose.prod.yml push

# Deploy on production server
docker-compose -f docker-compose.prod.yml up -d

# Monitor deployment
docker-compose -f docker-compose.prod.yml logs -f
```

#### Docker Deployment

**Container Resource Allocation:**

| Service | CPU | Memory | Disk | Network |
|---------|-----|--------|------|---------|
| Backend | 1-2 cores | 1-2GB | 1GB | 100Mbps |
| Binance Service | 1-2 cores | 1-2GB | 500MB | 100Mbps |
| Async Service | 1-2 cores | 1-2GB | 500MB | 100Mbps |
| Trade Service | 1-2 cores | 1-2GB | 1GB | 100Mbps |
| Trade Monitor | 0.5-1 core | 512MB-1GB | 500MB | 50Mbps |
| Frontend | 0.5-1 core | 512MB-1GB | 500MB | 50Mbps |
| MySQL | 2-4 cores | 2-4GB | 20GB+ | 100Mbps |
| Model Container | 0.5-1 core | 512MB-1GB | 500MB | 50Mbps |

**Docker Network Configuration:**

```bash
# Create custom network
docker network create --driver bridge \
  --subnet=172.20.0.0/16 \
  --gateway=172.20.0.1 \
  aifuturetrade-network

# Inspect network
docker network inspect aifuturetrade-network

# Connect container to network
docker network connect aifuturetrade-network <container_name>
```

**Volume Management:**

```bash
# List volumes
docker volume ls

# Backup MySQL data
docker run --rm \
  -v aifuturetrade_mysql_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/mysql-backup-$(date +%Y%m%d).tar.gz /data

# Restore MySQL data
docker run --rm \
  -v aifuturetrade_mysql_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/mysql-backup-20260225.tar.gz -C /
```

### ⚙️ Configuration

#### Environment Variables (.env)

```bash
# ============================================
# MySQL Database Configuration
# ============================================
MYSQL_HOST=localhost                # MySQL host (use 'mysql' for Docker internal)
MYSQL_PORT=3306                     # MySQL port
MYSQL_USER=aifuturetrade           # Database username
MYSQL_PASSWORD=your_password_here  # Database password (CHANGE IN PRODUCTION!)
MYSQL_DATABASE=aifuturetrade       # Database name
MYSQL_ROOT_PASSWORD=your_root_password_here  # Root password (CHANGE IN PRODUCTION!)

# ============================================
# Binance API Configuration
# ============================================
BINANCE_API_KEY=your_api_key_here           # Get from Binance account
BINANCE_API_SECRET=your_secret_key_here     # Keep this secret!
BINANCE_TESTNET=false                        # Use testnet for testing
BINANCE_BASE_URL=https://fapi.binance.com   # Futures API endpoint

# ============================================
# Service Ports Configuration
# ============================================
BACKEND_PORT=5002                   # Backend API port
BINANCE_SERVICE_PORT=5004          # Binance service port
ASYNC_SERVICE_PORT=5003            # Async service port
TRADE_PORT=5000                    # Trade service port
FRONTEND_PORT=3000                 # Frontend port

# ============================================
# Async Service Configuration
# ============================================
ASYNC_AUTO_START_ENABLED=true      # Auto-start async tasks on startup
ASYNC_AUTO_START_TASK=all          # Tasks to start: all, ticker, price, cleanup
ASYNC_TICKER_INTERVAL=1000         # Ticker update interval (ms)
ASYNC_PRICE_REFRESH_CRON=0 */5 * * * *    # Price refresh cron (every 5 min)
ASYNC_CLEANUP_CRON=0 */30 * * * *         # Cleanup cron (every 30 min)

# ============================================
# Trading Configuration
# ============================================
TRADE_MAX_POSITION_SIZE=10000      # Maximum position size (USDT)
TRADE_DEFAULT_LEVERAGE=10          # Default leverage
TRADE_RISK_PERCENT=2               # Risk per trade (%)
TRADE_SLIPPAGE_TOLERANCE=0.1       # Slippage tolerance (%)

# ============================================
# Security Configuration
# ============================================
JWT_SECRET=your_jwt_secret_key_here_change_in_production
JWT_EXPIRATION=86400               # JWT expiration (seconds, 24 hours)
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# ============================================
# Logging Configuration
# ============================================
LOG_LEVEL=INFO                     # DEBUG, INFO, WARN, ERROR
LOG_FILE_PATH=/var/log/aifuturetrade
LOG_MAX_FILE_SIZE=100MB
LOG_MAX_HISTORY=30                 # Days to keep logs

# ============================================
# Performance Configuration
# ============================================
THREAD_POOL_SIZE=20                # Thread pool size for async tasks
CONNECTION_POOL_SIZE=20            # Database connection pool size
CACHE_ENABLED=true                 # Enable caching
CACHE_TTL=300                      # Cache TTL (seconds)
```

#### Application Configuration (application.yml)

**Backend Service (backend/src/main/resources/application.yml):**

```yaml
server:
  port: ${BACKEND_PORT:5002}
  compression:
    enabled: true
  tomcat:
    threads:
      max: 200
      min-spare: 10

spring:
  application:
    name: aifuturetrade-backend
  datasource:
    url: jdbc:mysql://${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}?useSSL=false&serverTimezone=UTC&allowPublicKeyRetrieval=true
    username: ${MYSQL_USER}
    password: ${MYSQL_PASSWORD}
    driver-class-name: com.mysql.cj.jdbc.Driver
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000

mybatis-plus:
  configuration:
    map-underscore-to-camel-case: true
    log-impl: org.apache.ibatis.logging.slf4j.Slf4jImpl
  global-config:
    db-config:
      id-type: auto
      logic-delete-value: 1
      logic-not-delete-value: 0

logging:
  level:
    root: INFO
    com.aifuturetrade: DEBUG
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n"
```

#### JVM Parameters

**Backend Service:**
```bash
JAVA_OPTS="-Xms512m -Xmx1024m \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/heapdump.hprof \
  --add-opens java.base/java.lang.invoke=ALL-UNNAMED"
```

**Binance/Async Service:**
```bash
JAVA_OPTS="-Xms1g -Xmx2g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -XX:+UseStringDeduplication \
  -XX:+ParallelRefProcEnabled \
  --add-opens java.base/java.lang.invoke=ALL-UNNAMED"
```

### 📚 API Documentation

#### Authentication

All API requests (except public endpoints) require authentication using JWT tokens.

**Login Flow:**

```bash
# 1. Register user
curl -X POST http://localhost:5002/api/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader1",
    "password": "SecurePass123!",
    "email": "trader1@example.com",
    "initialCapital": 10000
  }'

# 2. Login to get JWT token
curl -X POST http://localhost:5002/api/users/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader1",
    "password": "SecurePass123!"
  }'

# Response:
{
  "code": 200,
  "message": "Login successful",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "userId": 1,
    "username": "trader1",
    "expiresIn": 86400
  }
}

# 3. Use token in subsequent requests
curl -X GET http://localhost:5002/api/users/profile \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

#### API Endpoints

**User Management**

```bash
# Register new user
POST /api/users/register
Content-Type: application/json

{
  "username": "string",
  "password": "string",
  "email": "string",
  "initialCapital": 10000.00
}

# Response: 200 OK
{
  "code": 200,
  "message": "User registered successfully",
  "data": {
    "userId": 1,
    "username": "trader1",
    "email": "trader1@example.com"
  }
}

# Login
POST /api/users/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}

# Get user profile
GET /api/users/profile
Authorization: Bearer {token}

# Response: 200 OK
{
  "code": 200,
  "data": {
    "userId": 1,
    "username": "trader1",
    "email": "trader1@example.com",
    "initialCapital": 10000.00,
    "currentBalance": 10523.45,
    "totalPnl": 523.45,
    "winRate": 65.5,
    "totalTrades": 42
  }
}
```

**Model Management**

```bash
# Create trading model
POST /api/models
Authorization: Bearer {token}
Content-Type: application/json

{
  "modelName": "BTC Long Strategy",
  "modelType": "BUY",
  "symbol": "BTCUSDT",
  "leverage": 10,
  "strategyParams": {
    "indicator": "RSI",
    "period": 14,
    "overbought": 70,
    "oversold": 30,
    "stopLoss": 2.0,
    "takeProfit": 5.0
  }
}

# Response: 201 Created
{
  "code": 201,
  "message": "Model created successfully",
  "data": {
    "modelId": 1,
    "modelName": "BTC Long Strategy",
    "status": "CREATED",
    "containerId": "buy-1"
  }
}

# List all models
GET /api/models?page=1&size=10
Authorization: Bearer {token}

# Get model details
GET /api/models/{id}
Authorization: Bearer {token}

# Start model container
POST /api/models/{id}/start
Authorization: Bearer {token}

# Response: 200 OK
{
  "code": 200,
  "message": "Model started successfully",
  "data": {
    "modelId": 1,
    "status": "RUNNING",
    "containerId": "buy-1",
    "startTime": "2026-02-25T10:30:00Z"
  }
}

# Stop model container
POST /api/models/{id}/stop
Authorization: Bearer {token}

# Delete model
DELETE /api/models/{id}
Authorization: Bearer {token}
```

**Trading Operations**

```bash
# Execute trade
POST /api/trades/execute
Authorization: Bearer {token}
Content-Type: application/json

{
  "modelId": 1,
  "symbol": "BTCUSDT",
  "side": "BUY",
  "type": "LIMIT",
  "quantity": 0.1,
  "price": 50000.00,
  "timeInForce": "GTC"
}

# Response: 200 OK
{
  "code": 200,
  "message": "Trade executed successfully",
  "data": {
    "tradeId": 1001,
    "orderId": "12345678",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": 0.1,
    "price": 50000.00,
    "status": "FILLED",
    "commission": 0.5,
    "timestamp": "2026-02-25T10:35:00Z"
  }
}

# Get trade history
GET /api/trades/history?symbol=BTCUSDT&startTime=1708848000000&endTime=1708934400000&page=1&size=20
Authorization: Bearer {token}

# Get current positions
GET /api/positions?modelId=1
Authorization: Bearer {token}

# Response: 200 OK
{
  "code": 200,
  "data": [
    {
      "positionId": 1,
      "symbol": "BTCUSDT",
      "positionSide": "LONG",
      "positionAmt": 0.1,
      "entryPrice": 50000.00,
      "markPrice": 51000.00,
      "unrealizedPnl": 100.00,
      "leverage": 10,
      "marginType": "ISOLATED"
    }
  ]
}

# Close position
POST /api/positions/close
Authorization: Bearer {token}
Content-Type: application/json

{
  "positionId": 1,
  "quantity": 0.1,
  "type": "MARKET"
}
```

**Market Data**

```bash
# Get K-line data
GET /api/market/klines?symbol=BTCUSDT&interval=1h&limit=100
Authorization: Bearer {token}

# Response: 200 OK
{
  "code": 200,
  "data": [
    {
      "openTime": 1708848000000,
      "open": "50000.00",
      "high": "51000.00",
      "low": "49500.00",
      "close": "50500.00",
      "volume": "1234.56",
      "closeTime": 1708851599999,
      "quoteVolume": "62345678.90"
    }
  ]
}

# Get ticker price
GET /api/market/ticker?symbol=BTCUSDT
Authorization: Bearer {token}

# Get 24-hour statistics
GET /api/market/24hr?symbol=BTCUSDT
Authorization: Bearer {token}

# Response: 200 OK
{
  "code": 200,
  "data": {
    "symbol": "BTCUSDT",
    "priceChange": "1000.00",
    "priceChangePercent": "2.00",
    "lastPrice": "51000.00",
    "volume": "123456.78",
    "quoteVolume": "6234567890.12",
    "openTime": 1708848000000,
    "closeTime": 1708934400000
  }
}
```

#### Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 200 | Success | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Authentication required or token invalid |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource already exists |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service temporarily unavailable |

**Error Response Format:**

```json
{
  "code": 400,
  "message": "Invalid request parameters",
  "error": "INVALID_PARAMETER",
  "details": {
    "field": "quantity",
    "reason": "Quantity must be greater than 0"
  },
  "timestamp": "2026-02-25T10:30:00Z"
}
```

#### Rate Limiting

- **Public endpoints**: 100 requests per minute per IP
- **Authenticated endpoints**: 1000 requests per minute per user
- **Trading endpoints**: 50 requests per minute per user
- **WebSocket connections**: 5 connections per user

**Rate Limit Headers:**

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1708934400
```

#### Swagger Documentation

Access interactive API documentation:
- **Backend**: http://localhost:5002/swagger-ui.html
- **Binance Service**: http://localhost:5004/swagger-ui.html
- **Trade Service**: http://localhost:5000/api/docs

### 💖 Sponsorship Support

If this project has been helpful to you, please consider supporting its continued development and maintenance:

<div align="center">

<table>
  <tr>
    <td align="center">
      <img src="img/contact.jpg" alt="Contact" width="50%" />
    </td>
    <td align="center">
      <img src="img/receive.jpg" alt="Sponsorship Support" width="50%" />
    </td>
  </tr>
</table>

**Thank you for your support! Your sponsorship will be used for:**
- 🚀 Continuous optimization of trading strategies and algorithms
- 🔧 Bug fixes and user experience improvements
- 📚 Documentation and tutorial enhancements
- 💡 Development of new features and capabilities

</div>

---

