#!/bin/bash

# 停止KLineChart Pro项目的脚本
# 关闭占用8000端口和8080端口的服务

echo "正在停止KLineChart Pro项目的服务..."

# 查找并关闭占用8000端口的进程（后端服务）
echo "正在关闭占用8000端口的后端服务..."
PORT_8000_PIDS=$(lsof -ti:8000)
if [ ! -z "$PORT_8000_PIDS" ]; then
  kill -9 $PORT_8000_PIDS
  echo "已关闭占用8000端口的进程: $PORT_8000_PIDS"
else
  echo "未找到占用8000端口的进程"
fi

# 查找并关闭占用8080端口的进程（前端服务）
echo "正在关闭占用8080端口的前端服务..."
PORT_8080_PIDS=$(lsof -ti:8080)
if [ ! -z "$PORT_8080_PIDS" ]; then
  kill -9 $PORT_8080_PIDS
  echo "已关闭占用8080端口的进程: $PORT_8080_PIDS"
else
  echo "未找到占用8080端口的进程"
fi

echo "服务关闭完成"