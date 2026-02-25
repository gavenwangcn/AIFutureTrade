package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.StrategyDecisionDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;

/**
 * Mapper接口：策略决策
 * 对应表名：strategy_decisions
 */
@Mapper
public interface StrategyDecisionMapper extends BaseMapper<StrategyDecisionDO> {

    /**
     * 更新策略决策记录状态，并可选写入 trade_id / error_reason
     *
     * @param decisionId 决策ID
     * @param status 新状态（EXECUTED/REJECTED）
     * @param tradeId 关联的交易记录ID（可选）
     * @param errorReason 错误原因（可选）
     * @return 更新的记录数
     */
    @Update("UPDATE strategy_decisions SET status = #{status}, trade_id = #{tradeId}, error_reason = #{errorReason}, updated_at = NOW() WHERE id = #{decisionId}")
    int updateStrategyDecisionStatus(@Param("decisionId") String decisionId,
                                     @Param("status") String status,
                                     @Param("tradeId") String tradeId,
                                     @Param("errorReason") String errorReason);

    /**
     * 删除与已取消条件单相关的策略决策记录
     * 删除条件：关联的条件单状态为CANCELLED且创建时间在指定时间之前
     *
     * @param beforeTime 时间阈值（删除此时间之前创建的记录）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM strategy_decisions WHERE id IN (" +
            "SELECT strategy_decision_id FROM algo_order " +
            "WHERE algoStatus = 'CANCELLED' AND created_at < #{beforeTime} AND strategy_decision_id IS NOT NULL)")
    int deleteByRelatedCancelledOrders(@Param("beforeTime") LocalDateTime beforeTime);
}
