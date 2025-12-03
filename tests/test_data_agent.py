import asyncio
import json
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_data_agent():
    """测试data_agent功能的简化版本"""
    from data.data_agent import DataAgentKlineManager
    from common.database_clickhouse import ClickHouseDatabase
    
    # 初始化数据库和kline_manager
    db = ClickHouseDatabase()
    kline_manager = DataAgentKlineManager(db, max_connections=10)
    
    # 创建事件用于等待数据
    data_received_event = asyncio.Event()
    received_data = None
    
    # 保存原有消息处理器
    original_handle_message = kline_manager._handle_kline_message
    
    # 定义新的消息处理器，用于捕获K线数据
    async def new_handle_message(symbol, interval, message):
        nonlocal received_data
        # 调用原有消息处理器
        await original_handle_message(symbol, interval, message)
        
        # 捕获并保存K线数据
        received_data = {
            "symbol": symbol,
            "interval": interval,
            "message": str(message),  # 简单转换为字符串，避免序列化问题
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"接收到真实数据: {symbol} {interval}")
        
        # 设置事件，表示已收到数据
        data_received_event.set()
    
    # 替换消息处理器
    kline_manager._handle_kline_message = new_handle_message
    logger.info("DataAgent测试已启动，消息处理器已替换")
    
    try:
        # 添加K线流
        symbol = "BTCUSDT"
        interval = "1m"
        
        logger.info(f"添加K线流: {symbol} {interval}")
        success = await kline_manager.add_stream(symbol, interval)
        
        if success:
            logger.info(f"添加K线流成功: {symbol} {interval}")
            
            # 等待接收数据，超时时间60秒
            logger.info(f"等待接收K线数据，超时时间: 60秒")
            try:
                await asyncio.wait_for(data_received_event.wait(), timeout=60)
                logger.info("成功接收到K线数据")
                
                # 打印接收到的数据
                logger.info(f"接收到的K线数据: {json.dumps(received_data, indent=2, ensure_ascii=False)}")
                
                logger.info("测试成功: 成功添加K线流并接收数据")
            except asyncio.TimeoutError:
                logger.error("等待K线数据超时")
        else:
            logger.error(f"添加K线流失败: {symbol} {interval}")
    
    finally:
        # 恢复原有消息处理器
        kline_manager._handle_kline_message = original_handle_message
        
        # 清理所有连接
        await kline_manager.cleanup_all()
        logger.info("DataAgent测试已停止，资源已清理")

if __name__ == "__main__":
    asyncio.run(test_data_agent())