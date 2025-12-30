#!/bin/bash

echo "============================================"
echo "🩺 Async Service 诊断工具"
echo "============================================"

echo ""
echo "1️⃣ 检查Docker服务状态..."
docker-compose ps

echo ""
echo "2️⃣ 检查Async Service日志（最近20行）..."
docker-compose logs --tail=20 async-service

echo ""
echo "3️⃣ 检查环境变量配置..."
docker-compose exec -T async-service env | grep -E "(BINANCE|DATABASE)" || echo "未找到相关环境变量"

echo ""
echo "4️⃣ 测试API连接..."
curl -s http://localhost:5003/actuator/health || echo "❌ Async Service未响应"

echo ""
echo "5️⃣ 检查任务状态..."
curl -s http://localhost:5003/api/async/status || echo "❌ 无法获取任务状态"

echo ""
echo "6️⃣ 尝试手动启动market_tickers任务..."
curl -s -X POST http://localhost:5003/api/async/task/market_tickers || echo "❌ 启动失败"

echo ""
echo "7️⃣ 再次检查任务状态..."
curl -s http://localhost:5003/api/async/task/market_tickers/status || echo "❌ 无法获取状态"

echo ""
echo "============================================"
echo "🏁 诊断完成，请根据上述结果进行分析"
echo "============================================"