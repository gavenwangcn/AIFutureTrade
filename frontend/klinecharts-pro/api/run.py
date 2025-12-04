"""
启动Flask应用的脚本
"""
from main import app

if __name__ == "__main__":
    # 使用main.py中定义的配置运行应用
    app.run(host="127.0.0.1", port=8000, debug=True)