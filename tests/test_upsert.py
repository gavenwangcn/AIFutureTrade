#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试upsert_market_tickers方法的功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database_clickhouse import DatabaseClickHouse
import logging
import time

# 配置日志
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_upsert_market_tickers():
    """测试upsert_market_tickers方法"""
    logger.info("开始测试upsert_market_tickers方法...")
    
    # 创建数据库连接
    db = DatabaseClickHouse()
    
    # 测试数据1：新数据（应该执行INSERT）
    test_data1 = [
        {
            'event_time': 1690000000000,
            'symbol': 'TESTUSDT',
            'open_price': 100.0,
            'high_price': 110.0,
            'low_price': 90.0,
            'last_price': 105.0,
            'volume': 1000.0,
            'quote_volume': 105000.0,
            'trade_count': 100,
            'update_price_date': '2023-07-23'
        }
    ]
    
    # 测试数据2：更新数据（应该执行UPDATE）
    test_data2 = [
        {
            'event_time': 1690000001000,
            'symbol': 'TESTUSDT',
            'open_price': 100.0,  # 保持不变，由异步服务更新
            'high_price': 120.0,  # 新的最高价
            'low_price': 85.0,    # 新的最低价
            'last_price': 110.0,  # 新的最新价
            'volume': 2000.0,     # 新的成交量
            'quote_volume': 220000.0,  # 新的成交额
            'trade_count': 200,   # 新的成交笔数
            'update_price_date': '2023-07-23'  # 保持不变，由异步服务更新
        }
    ]
    
    try:
        # 1. 测试插入新数据
        logger.info("测试1: 插入新数据")
        result1 = db.upsert_market_tickers(test_data1)
        logger.info(f"插入结果: {result1}")
        
        # 验证数据是否插入成功
        query = "SELECT * FROM 24_market_tickers WHERE symbol = 'TESTUSDT'"
        result = db.query(query)
        logger.info(f"验证插入结果: {len(result)} 行数据")
        if result:
            logger.info(f"数据详情: {result[0]}")
        
        time.sleep(1)  # 等待一下
        
        # 2. 测试更新已有数据
        logger.info("测试2: 更新已有数据")
        result2 = db.upsert_market_tickers(test_data2)
        logger.info(f"更新结果: {result2}")
        
        # 验证数据是否更新成功
        result = db.query(query)
        logger.info(f"验证更新结果: {len(result)} 行数据")
        if result:
            logger.info(f"数据详情: {result[0]}")
            # 检查last_price是否已更新
            last_price = float(result[0][5])  # last_price在第6列
            logger.info(f"更新后的last_price: {last_price}")
            if last_price == 110.0:
                logger.info("✓ last_price已正确更新")
            else:
                logger.warning("✗ last_price未更新")
        
        # 3. 清理测试数据
        logger.info("测试3: 清理测试数据")
        delete_query = "ALTER TABLE 24_market_tickers DELETE WHERE symbol = 'TESTUSDT'"
        db.command(delete_query)
        logger.info("测试数据已清理")
        
        # 验证清理结果
        result = db.query(query)
        logger.info(f"验证清理结果: {len(result)} 行数据")
        
        logger.info("所有测试完成！")
        return True
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_upsert_market_tickers()
    sys.exit(0 if success else 1)
