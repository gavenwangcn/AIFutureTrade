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
     * 更新条件订单的trade_id和状态
     * 
     * @param id 订单ID
     * @param tradeId 交易记录ID
     * @param algoStatus 新状态
     * @return 更新的记录数
     */
    @Update("UPDATE algo_order SET trade_id = #{tradeId}, algoStatus = #{algoStatus}, updated_at = NOW() WHERE id = #{id}")
    int updateTradeIdAndStatus(@Param("id") String id, @Param("tradeId") String tradeId, @Param("algoStatus") String algoStatus);
}
