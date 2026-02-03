package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.AlgoOrderDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/**
 * Mapper接口：条件订单
 * 对应表名：algo_order
 */
@Mapper
public interface AlgoOrderMapper extends BaseMapper<AlgoOrderDO> {

    /**
     * 查询所有状态为"new"的条件订单
     * 
     * @return 条件订单列表
     */
    List<AlgoOrderDO> selectNewAlgoOrders();

    /**
     * 更新条件订单状态
     * 
     * @param id 订单ID
     * @param algoStatus 新状态
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET algoStatus = #{algoStatus}, updated_at = NOW() WHERE id = #{id}")
    int updateAlgoStatus(@Param("id") String id, @Param("algoStatus") String algoStatus);

    /**
     * 更新条件订单状态和错误原因
     *
     * @param id 订单ID
     * @param algoStatus 新状态
     * @param errorReason 错误原因
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET algoStatus = #{algoStatus}, error_reason = #{errorReason}, updated_at = NOW() WHERE id = #{id}")
    int updateAlgoStatusWithError(@Param("id") String id, @Param("algoStatus") String algoStatus, @Param("errorReason") String errorReason);

    /**
     * 更新条件订单的trade_id和状态
     *
     * @param id 订单ID
     * @param tradeId 交易记录ID
     * @param algoStatus 新状态
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET trade_id = #{tradeId}, algoStatus = #{algoStatus}, updated_at = NOW() WHERE id = #{id}")
    int updateTradeIdAndStatus(@Param("id") String id, @Param("tradeId") String tradeId, @Param("algoStatus") String algoStatus);

    /**
     * 查询指定模型和交易对的状态为"new"的条件订单
     * 
     * @param modelId 模型ID
     * @param symbol 交易对符号
     * @return 条件订单列表
     */
    @org.apache.ibatis.annotations.Select("SELECT id, algoId, clientAlgoId, type, algoType, orderType, " +
            "symbol, side, positionSide, quantity, algoStatus, " +
            "triggerPrice, price, model_id, strategy_decision_id, trade_id, " +
            "created_at, updated_at " +
            "FROM algo_order " +
            "WHERE model_id = #{modelId} AND symbol = #{symbol} AND algoStatus = 'new' " +
            "ORDER BY created_at ASC")
    List<AlgoOrderDO> selectNewAlgoOrdersByModelAndSymbol(@Param("modelId") String modelId, @Param("symbol") String symbol);

    /**
     * 更新条件订单状态为cancelled
     * 
     * @param id 订单ID
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET algoStatus = 'cancelled', updated_at = NOW() WHERE id = #{id}")
    int updateAlgoStatusToCancelled(@Param("id") String id);
}
