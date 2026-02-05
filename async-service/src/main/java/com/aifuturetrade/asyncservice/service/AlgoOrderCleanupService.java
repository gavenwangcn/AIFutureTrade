package com.aifuturetrade.asyncservice.service;

/**
 * 条件订单清理服务接口
 *
 * 负责定期清理已取消的历史条件订单
 */
public interface AlgoOrderCleanupService {

    /**
     * 清理已取消的历史条件订单
     * 删除状态为CANCELLED且创建时间超过配置时长的订单
     *
     * @return 清理结果
     */
    CleanupResult cleanupCancelledOrders();

    /**
     * 启动定时清理任务
     */
    void startScheduler();

    /**
     * 停止定时清理任务
     */
    void stopScheduler();

    /**
     * 清理结果
     */
    class CleanupResult {
        private final int deletedCount;
        private final boolean success;
        private final String message;

        public CleanupResult(int deletedCount, boolean success, String message) {
            this.deletedCount = deletedCount;
            this.success = success;
            this.message = message;
        }

        public int getDeletedCount() {
            return deletedCount;
        }

        public boolean isSuccess() {
            return success;
        }

        public String getMessage() {
            return message;
        }
    }
}
