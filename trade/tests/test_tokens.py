#!/usr/bin/env python3
import requests
import json
import time

def test_max_tokens(base_url, api_key, model_name):
    """测试模型的最大token限制"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 测试不同输入长度
    test_lengths = [100, 1000, 5000, 10000, 20000, 30000, 40000, 
                    50000, 60000, 70000, 80000, 100000, 128000]
    
    print("测试输入token限制...")
    for length in test_lengths:
        # 生成测试文本
        test_text = "测试 " * (length // 2)
        
        payload = {
            "model": model_name,
            "prompt": test_text,
            "max_tokens": 10,  # 只生成少量token来测试输入限制
            "temperature": 0
        }
        
        try:
            response = requests.post(
                f"{base_url}/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ 输入长度 {length} token: 成功")
            else:
                error_msg = response.json().get('error', {}).get('message', '未知错误')
                print(f"✗ 输入长度 {length} token: 失败 - {error_msg}")
                break
                
        except Exception as e:
            print(f"✗ 输入长度 {length} token: 异常 - {str(e)}")
            break
        
        time.sleep(0.5)

def test_context_window(base_url, api_key, model_name):
    """测试总上下文窗口大小"""
    print("\n测试总上下文窗口...")
    
    # 使用二分查找快速找到边界
    low, high = 1000, 200000
    max_success = 0
    
    while low <= high:
        mid = (low + high) // 2
        test_text = "A" * mid
        
        payload = {
            "model": model_name,
            "prompt": test_text[:1000],  # 只取前1000字符避免请求过大
            "max_tokens": 10,
            "temperature": 0
        }
        
        try:
            response = requests.post(
                f"{base_url}/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                max_success = mid
                low = mid + 1000
                print(f"  {mid} token: 成功")
            else:
                high = mid - 1000
                print(f"  {mid} token: 失败")
                
        except Exception as e:
            high = mid - 1000
            
        time.sleep(0.5)
    
    print(f"\n估计最大上下文窗口: {max_success} token")

if __name__ == "__main__":
    BASE_URL = "http://115.120.51.164:30004/v1"
    API_KEY = "ZGQ3NjYyOGJlMjg2ZDk4ZTAxOWVhNzE4YWY0NzM1MGUzNjNhMzRjOA=="
    MODEL_NAME = "chery3-v3-671b"
    
    test_max_tokens(BASE_URL, API_KEY, MODEL_NAME)
    test_context_window(BASE_URL, API_KEY, MODEL_NAME)