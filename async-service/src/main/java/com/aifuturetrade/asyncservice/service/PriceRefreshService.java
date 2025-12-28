package com.aifuturetrade.asyncservice.service;

/**
 * 价格刷新服务接口
 * 
 * 负责定期刷新24_market_tickers表的开盘价格。
 * 通过获取币安期货的日K线数据，使用昨天的收盘价作为今天的开盘价。
 * 
 * 主要功能：
 * - 查询需要刷新价格的symbol列表
 * - 获取日K线数据并更新open_price
 * - 批量处理，控制刷新频率
 * - 定时调度执行
 */
public interface PriceRefreshService {
    
    /**
     * 刷新所有需要更新价格的symbol
     * 
     * @return 刷新结果统计
     */
    RefreshResult refreshAllPrices();
    
    /**
     * 刷新单个symbol的开盘价格
     * 
     * @param symbol 交易对符号
     * @return true如果刷新成功，false否则
     */
    boolean refreshPriceForSymbol(String symbol);
    
    /**
     * 启动定时刷新调度器
     */
    void startScheduler();
    
    /**
     * 停止定时刷新调度器
     */
    void stopScheduler();
    
    /**
     * 刷新结果统计
     */
    class RefreshResult {
        private int total;
        private int success;
        private int failed;
        
        public RefreshResult(int total, int success, int failed) {
            this.total = total;
            this.success = success;
            this.failed = failed;
        }
        
        public int getTotal() { return total; }
        public int getSuccess() { return success; }
        public int getFailed() { return failed; }
    }
}

