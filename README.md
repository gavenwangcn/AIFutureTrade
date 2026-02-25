# AIFutureTrade - AI-Powered Cryptocurrency Futures Trading System

<div align="center">

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Java](https://img.shields.io/badge/Java-17-orange.svg)](https://www.oracle.com/java/)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-green.svg)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

An intelligent automated trading system for Binance Futures, powered by AI and built with microservices architecture.

[English](#english) | [中文](#chinese)

</div>

---

## <a name="english"></a>English

### 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Development](#development)
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

### ✨ Features

#### Trading Features
- **AI-Driven Strategies**: Dynamic buy/sell models with independent container execution
- **Risk Management**: Position sizing, stop-loss, and take-profit automation
- **Multi-Symbol Support**: Trade multiple futures contracts simultaneously
- **Real-time Execution**: Low-latency order placement and management

#### Data Processing
- **WebSocket Streaming**: Real-time market ticker data from Binance
- **Historical Data**: K-line data storage and analysis
- **Technical Indicators**: Built-in TA-Lib integration for technical analysis
- **Data Persistence**: MySQL database for trade history and positions

#### System Features
- **Microservices Architecture**: Independent, scalable services
- **Dynamic Container Management**: Auto-scaling trading model containers
- **Health Monitoring**: Service status tracking and auto-restart
- **RESTful APIs**: Comprehensive API endpoints with Swagger documentation

### 🏗️ Architecture

#### System Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        FE[Vue 3 Frontend<br/>Port 3000]
    end

    subgraph "API Gateway Layer"
        BE[Backend Service<br/>Java Spring Boot<br/>Port 5002]
    end

    subgraph "Core Services"
        BS[Binance Service<br/>Market Data API<br/>Port 5004]
        AS[Async Service<br/>WebSocket Stream<br/>Port 5003]
        TS[Trade Service<br/>Python Flask<br/>Port 5000]
    end

    subgraph "Dynamic Trading Models"
        MB1[Model Buy Container 1]
        MB2[Model Buy Container 2]
        MS1[Model Sell Container 1]
        MS2[Model Sell Container 2]
    end

    subgraph "External Services"
        BINANCE[Binance API<br/>Futures Market]
        DB[(MySQL Database<br/>Port 32123)]
    end

    FE -->|HTTP/WebSocket| BE
    BE -->|REST API| TS
    BE -->|REST API| BS
    BE -->|Docker API| MB1
    BE -->|Docker API| MB2
    BE -->|Docker API| MS1
    BE -->|Docker API| MS2
    BE -->|JDBC| DB

    BS -->|HTTPS| BINANCE
    AS -->|WebSocket| BINANCE
    AS -->|JDBC| DB
    TS -->|HTTPS| BINANCE
    TS -->|JDBC| DB

    MB1 -->|Trade Logic| TS
    MB2 -->|Trade Logic| TS
    MS1 -->|Trade Logic| TS
    MS2 -->|Trade Logic| TS

    style FE fill:#42b983
    style BE fill:#ff6b6b
    style BS fill:#4ecdc4
    style AS fill:#95e1d3
    style TS fill:#f38181
    style BINANCE fill:#ffd93d
    style DB fill:#6c5ce7
```
