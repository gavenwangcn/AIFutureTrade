# AIFutureTrade - AI-Powered Cryptocurrency Futures Trading System

<div align="center">

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Java](https://img.shields.io/badge/Java-17-orange.svg)](https://www.oracle.com/java/)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-green.svg)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.2.0-brightgreen.svg)](https://spring.io/projects/spring-boot)

An intelligent automated trading system for Binance Futures, powered by AI and built with microservices architecture.

[English](#english) | [中文](#chinese)

</div>

---

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
            MB[buy-{modelId}]
            MS[sell-{modelId}]
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
- **KLineChart 9.5.0**: Professional candlestick charting
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
MYSQL_HOST=154.89.148.172          # MySQL host (use 'mysql' for Docker internal)
MYSQL_PORT=32123                    # MySQL port
MYSQL_USER=aifuturetrade           # Database username
MYSQL_PASSWORD=aifuturetrade123    # Database password (CHANGE IN PRODUCTION!)
MYSQL_DATABASE=aifuturetrade       # Database name
MYSQL_ROOT_PASSWORD=root123        # Root password (CHANGE IN PRODUCTION!)

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

