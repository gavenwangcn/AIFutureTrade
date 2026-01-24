package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.TradeDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：交易记录
 * 对应表名：trades
 */
@Mapper
public interface TradeMapper extends BaseMapper<TradeDO> {

    /**
     * 根据模型ID查询交易记录，按照时间倒序排列
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 交易记录列表
     */
    @Select("select * from trades where model_id = #{modelId} order by timestamp desc limit #{limit}")
    List<TradeDO> selectTradesByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);
    
    /**
     * 根据模型ID统计交易记录总数
     * @param modelId 模型ID（UUID格式）
     * @return 交易记录总数
     */
    @Select("select count(*) from trades where model_id = #{modelId}")
    Long countTradesByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID删除交易记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM trades WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID查询交易统计信息（直接基于trades表，按signal分组统计）
     * 只统计卖出类型交易（trades.side = 'sell'），因为只有卖出交易才有实际的盈亏（pnl）
     * 按signal分组统计：交易次数、胜率、平均盈利、平均亏损、盈亏比、期望值
     * @param modelId 模型ID（UUID格式）
     * @return 策略统计信息列表，每个元素包含：strategy_name（使用signal作为策略名称）, trade_count, win_rate, avg_profit, avg_loss, profit_loss_ratio, expected_value
     */
    @Select("SELECT " +
            "    COALESCE(t.signal, '未知策略') as strategy_name, " +
            "    COUNT(t.id) as trade_count, " +
            "    CASE " +
            "        WHEN COUNT(t.id) = 0 THEN NULL " +
            "        ELSE CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id) " +
            "    END as win_rate, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) " +
            "    END as avg_profit, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) " +
            "    END as avg_loss, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE ABS((SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) / " +
            "             NULLIF((SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)), 0)) " +
            "    END as profit_loss_ratio, " +
            "    CASE " +
            "        WHEN COUNT(t.id) = 0 THEN NULL " +
            "        WHEN (CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE (CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) * " +
            "             (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) - " +
            "             (1 - CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) * " +
            "             ABS(SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) " +
            "    END as expected_value " +
            "FROM trades t " +
            "WHERE t.model_id = #{modelId} " +
            "    AND t.side = 'sell' " +
            "GROUP BY t.signal " +
            "ORDER BY trade_count DESC")
    List<Map<String, Object>> selectStrategyAnalysisByModelId(@Param("modelId") String modelId);

    /**
     * 查询所有模型的分析数据（每个模型一行）
     *
     * 统计口径（只统计卖出类型交易：trades.side = 'sell'）：
     * - 交易次数：该模型卖出交易总数
     * - 胜率：卖出交易中 pnl>0 的笔数 / 卖出交易总笔数
     * - 平均盈利：卖出交易中 pnl>0 的 pnl 总和 / pnl>0 的笔数
     * - 平均亏损：卖出交易中 pnl<0 的 pnl 总和 / pnl<0 的笔数
     * - 盈亏比：平均盈利 / 平均亏损（取绝对值）
     * - 期望值：EV = (胜率 × 平均盈利) - ((1 - 胜率) × 平均亏损)
     *
     * @return 所有模型的统计信息列表，每个元素包含：model_id, model_name, trade_count, win_rate, avg_profit, avg_loss, profit_loss_ratio, expected_value
     */
    @Select("SELECT " +
            "    t.model_id as model_id, " +
            "    COALESCE(m.name, CONCAT('模型 ', t.model_id)) as model_name, " +
            "    COUNT(t.id) as trade_count, " +
            "    CASE " +
            "        WHEN COUNT(t.id) = 0 THEN NULL " +
            "        ELSE CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id) " +
            "    END as win_rate, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) " +
            "    END as avg_profit, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) " +
            "    END as avg_loss, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE ABS((SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) / " +
            "             NULLIF((SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)), 0)) " +
            "    END as profit_loss_ratio, " +
            "    CASE " +
            "        WHEN COUNT(t.id) = 0 THEN NULL " +
            "        WHEN (CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE (CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) * " +
            "             (SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)) - " +
            "             (1 - CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(t.id)) * " +
            "             ABS(SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END) / SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END)) " +
            "    END as expected_value " +
            "FROM trades t " +
            "LEFT JOIN models m ON t.model_id = m.id " +
            "WHERE t.side = 'sell' " +
            "GROUP BY t.model_id, m.name " +
            "ORDER BY trade_count DESC")
    List<Map<String, Object>> selectAllModelsAnalysis();

}