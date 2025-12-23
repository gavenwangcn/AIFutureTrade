package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AccountValueHistoryDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：账户价值历史记录
 */
@Mapper
public interface AccountValueHistoryMapper extends BaseMapper<AccountValueHistoryDO> {

    /**
     * 根据模型ID查询账户价值历史
     * 返回字段使用snake_case格式，与前端期望一致
     */
    @Select("SELECT id, model_id, account_alias, balance, available_balance, " +
            "cross_wallet_balance, cross_un_pnl, timestamp " +
            "FROM account_value_historys " +
            "WHERE model_id = #{modelId} " +
            "ORDER BY timestamp DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectHistoryByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);

    /**
     * 查询聚合账户价值历史（所有模型）
     * 返回字段使用snake_case格式，与前端期望一致
     */
    @Select("SELECT id, model_id, account_alias, balance, available_balance, " +
            "cross_wallet_balance, cross_un_pnl, timestamp " +
            "FROM account_value_historys " +
            "ORDER BY timestamp DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectAggregatedHistory(@Param("limit") Integer limit);

    /**
     * 查询多模型图表数据
     * 返回所有模型的历史记录，按时间倒序排列，用于图表显示
     * 返回字段使用snake_case格式，与前端期望一致
     */
    @Select("SELECT id, model_id, account_alias, balance, available_balance, " +
            "cross_wallet_balance, cross_un_pnl, timestamp " +
            "FROM account_value_historys " +
            "ORDER BY timestamp DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectMultiModelChartData(@Param("limit") Integer limit);

    /**
     * 根据模型ID删除账户价值历史记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM account_value_historys WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

