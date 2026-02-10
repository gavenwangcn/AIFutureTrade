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
     * 
     * 统计逻辑优化：同一个portfolios_id的多条卖出记录合并为1次交易
     * - 先按portfolios_id合并所有卖出记录的pnl（同一个portfolios_id算1次交易）
     * - 如果同一个portfolios_id对应多个signal，取第一个signal作为该交易的signal
     * - 交易次数：按portfolios_id分组后的交易数量（同一个portfolios_id算1次）
     * - 胜率：合并后交易中总pnl>0的交易数 / 合并后的交易总数
     * - 平均盈利：合并后交易中总pnl>0的交易的总pnl之和 / 盈利交易数
     * - 平均亏损：合并后交易中总pnl<0的交易的总pnl之和 / 亏损交易数
     * - 盈亏比：平均盈利 / 平均亏损（取绝对值）
     * - 期望值：EV = (胜率 × 平均盈利) - ((1 - 胜率) × 平均亏损)
     * 
     * @param modelId 模型ID（UUID格式）
     * @return 策略统计信息列表，每个元素包含：strategy_name（使用signal作为策略名称）, trade_count, win_rate, avg_profit, avg_loss, profit_loss_ratio, expected_value
     */
    @Select("SELECT " +
            "    COALESCE(merged.signal, '未知策略') as strategy_name, " +
            "    COUNT(merged.portfolios_id) as trade_count, " +
            "    CASE " +
            "        WHEN COUNT(merged.portfolios_id) = 0 THEN NULL " +
            "        ELSE CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id) " +
            "    END as win_rate, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) " +
            "    END as avg_profit, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) " +
            "    END as avg_loss, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE ABS((SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) / " +
            "             NULLIF((SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)), 0)) " +
            "    END as profit_loss_ratio, " +
            "    CASE " +
            "        WHEN COUNT(merged.portfolios_id) = 0 THEN NULL " +
            "        WHEN (CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE (CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) * " +
            "             (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) - " +
            "             (1 - CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) * " +
            "             ABS(SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) " +
            "    END as expected_value " +
            "FROM ( " +
            "    SELECT " +
            "        t.portfolios_id, " +
            "        MIN(t.signal) as signal, " +
            "        SUM(t.pnl) as total_pnl " +
            "    FROM trades t " +
            "    WHERE t.model_id = #{modelId} " +
            "        AND t.side = 'sell' " +
            "        AND t.portfolios_id IS NOT NULL " +
            "    GROUP BY t.portfolios_id " +
            ") merged " +
            "GROUP BY merged.signal " +
            "ORDER BY trade_count DESC")
    List<Map<String, Object>> selectStrategyAnalysisByModelId(@Param("modelId") String modelId);

    /**
     * 查询所有模型的分析数据（每个模型一行）
     *
     * 统计口径优化（只统计卖出类型交易：trades.side = 'sell'）：
     * 同一个portfolios_id的多条卖出记录合并为1次交易
     * - 交易次数：按portfolios_id分组后的交易数量（同一个portfolios_id算1次）
     * - 胜率：合并后交易中总pnl>0的交易数 / 合并后的交易总数
     * - 平均盈利：合并后交易中总pnl>0的交易的总pnl之和 / 盈利交易数
     * - 平均亏损：合并后交易中总pnl<0的交易的总pnl之和 / 亏损交易数
     * - 盈亏比：平均盈利 / 平均亏损（取绝对值）
     * - 期望值：EV = (胜率 × 平均盈利) - ((1 - 胜率) × 平均亏损)
     *
     * @return 所有模型的统计信息列表，每个元素包含：model_id, model_name, trade_count, win_rate, avg_profit, avg_loss, profit_loss_ratio, expected_value
     */
    @Select("SELECT " +
            "    merged.model_id as model_id, " +
            "    COALESCE(m.name, CONCAT('模型 ', merged.model_id)) as model_name, " +
            "    COUNT(merged.portfolios_id) as trade_count, " +
            "    CASE " +
            "        WHEN COUNT(merged.portfolios_id) = 0 THEN NULL " +
            "        ELSE CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id) " +
            "    END as win_rate, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) " +
            "    END as avg_profit, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        ELSE SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) " +
            "    END as avg_loss, " +
            "    CASE " +
            "        WHEN SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) = 0 THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE ABS((SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) / " +
            "             NULLIF((SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)), 0)) " +
            "    END as profit_loss_ratio, " +
            "    CASE " +
            "        WHEN COUNT(merged.portfolios_id) = 0 THEN NULL " +
            "        WHEN (CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        WHEN (SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) IS NULL THEN NULL " +
            "        ELSE (CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) * " +
            "             (SUM(CASE WHEN merged.total_pnl > 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END)) - " +
            "             (1 - CAST(SUM(CASE WHEN merged.total_pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(merged.portfolios_id)) * " +
            "             ABS(SUM(CASE WHEN merged.total_pnl < 0 THEN merged.total_pnl ELSE 0 END) / SUM(CASE WHEN merged.total_pnl < 0 THEN 1 ELSE 0 END)) " +
            "    END as expected_value " +
            "FROM ( " +
            "    SELECT " +
            "        t.model_id, " +
            "        t.portfolios_id, " +
            "        SUM(t.pnl) as total_pnl " +
            "    FROM trades t " +
            "    WHERE t.side = 'sell' " +
            "        AND t.portfolios_id IS NOT NULL " +
            "    GROUP BY t.model_id, t.portfolios_id " +
            ") merged " +
            "LEFT JOIN models m ON merged.model_id = m.id " +
            "GROUP BY merged.model_id, m.name " +
            "ORDER BY trade_count DESC")
    List<Map<String, Object>> selectAllModelsAnalysis();

}