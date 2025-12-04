#!/bin/bash

# 启动KLineChart Pro项目的脚本
# 包括后端API服务和前端页面

echo "正在启动KLineChart Pro项目..."

# 关闭可能正在运行的服务
echo "正在关闭占用8000端口的后端服务..."
PORT_8000_PIDS=$(lsof -ti:8000)
if [ ! -z "$PORT_8000_PIDS" ]; then
  kill -9 $PORT_8000_PIDS
  echo "已关闭占用8000端口的进程: $PORT_8000_PIDS"
else
  echo "未找到占用8000端口的进程"
fi

echo "正在关闭占用8080端口的前端服务..."
PORT_8080_PIDS=$(lsof -ti:8080)
if [ ! -z "$PORT_8080_PIDS" ]; then
  kill -9 $PORT_8080_PIDS
  echo "已关闭占用8080端口的进程: $PORT_8080_PIDS"
else
  echo "未找到占用8080端口的进程"
fi

# 等待一段时间确保端口被释放
echo "正在关闭现有服务..."
sleep 2

# 启动后端服务
echo "正在启动后端API服务..."
cd api
# 激活虚拟环境
source .venv/bin/activate
# 在后台启动后端服务
python main.py &
# 保存后端进程ID
BACKEND_PID=$!
cd ..

# 等待后端服务启动
echo "等待后端服务启动..."
sleep 2

# 启动前端服务
# 使用Python内置HTTP服务器在项目根目录启动前端
echo "正在启动前端服务..."
python -m http.server 8080 &
# 保存前端进程ID
FRONTEND_PID=$!

# 显示服务状态
echo "后端API服务已启动，PID: $BACKEND_PID，访问地址: http://localhost:8000"
echo "前端服务已启动，PID: $FRONTEND_PID，访问地址: http://localhost:8080"
echo "请在浏览器中打开 http://localhost:8080 查看KLineChart Pro"

# 等待用户按键后关闭服务
echo "按任意键关闭服务..."
read -n 1 -s

# 关闭服务
# 先尝试正常终止进程
kill $BACKEND_PID 2>/dev/null
kill $FRONTEND_PID 2>/dev/null

# 等待一段时间让进程正常关闭
sleep 3

# 检查进程是否仍在运行，如果仍在运行则强制终止
if ps -p $BACKEND_PID > /dev/null 2>&1; then
  echo "后端服务未正常关闭，正在强制终止..."
  kill -9 $BACKEND_PID 2>/dev/null
fi

if ps -p $FRONTEND_PID > /dev/null 2>&1; then
  echo "前端服务未正常关闭，正在强制终止..."
  kill -9 $FRONTEND_PID 2>/dev/null
fi

echo "服务已关闭"