package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AlgoOrderDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/**
 * Mapper接口：条件订单
 * 对应表名：algo_order
 */
@Mapper
public interface AlgoOrderMapper extends BaseMapper<AlgoOrderDO> {

    /**
     * 查询指定模型和交易对的状态为"new"的条件订单
     * 
     * @param modelId 模型ID
     * @param symbol 交易对符号
     * @return 条件订单列表
     */
    @Select("SELECT id, algoId, clientAlgoId, type, algoType, orderType, " +
            "symbol, side, positionSide, quantity, algoStatus, " +
            "triggerPrice, price, model_id, strategy_decision_id, trade_id, " +
            "created_at, updated_at " +
            "FROM algo_order " +
            "WHERE model_id = #{modelId} AND symbol = #{symbol} AND algoStatus = 'NEW' " +
            "ORDER BY created_at ASC")
    List<AlgoOrderDO> selectNewAlgoOrdersByModelAndSymbol(@Param("modelId") String modelId, @Param("symbol") String symbol);

    /**
     * 更新条件订单状态为cancelled
     * 
     * @param id 订单ID
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET algoStatus = 'CANCELLED', updated_at = NOW() WHERE id = #{id}")
    int updateAlgoStatusToCancelled(@Param("id") String id);

    /**
     * 批量更新条件订单状态为cancelled
     * 
     * @param ids 订单ID列表
     * @return 更新的记录数
     */
    @Update("<script>" +
            "UPDATE algo_order SET algoStatus = 'CANCELLED', updated_at = NOW() " +
            "WHERE id IN " +
            "<foreach collection='ids' item='id' open='(' separator=',' close=')'>" +
            "#{id}" +
            "</foreach>" +
            "</script>")
    int batchUpdateAlgoStatusToCancelled(@Param("ids") List<String> ids);

    /**
     * 根据模型ID统计条件订单总数
     * 
     * @param modelId 模型ID
     * @return 条件订单总数
     */
    @Select("SELECT COUNT(*) FROM algo_order WHERE model_id = #{modelId}")
    Long countAlgoOrdersByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID删除条件订单
     * 
     * @param modelId 模型ID
     * @return 删除的记录数
     */
    @Delete("DELETE FROM algo_order WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);
}
