package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AccountValuesDailyDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Mapper接口：账户每日价值记录
 * 对应表名：account_values_daily
 */
@Mapper
public interface AccountValuesDailyMapper extends BaseMapper<AccountValuesDailyDO> {

    /**
     * 获取当天的账户价值记录（当天指从早上8点到第二天早上8点）
     * 
     * @param modelId 模型ID（UUID格式）
     * @param todayStart 当天开始时间（早上8点，UTC+8时区）
     * @return 包含balance和available_balance的Map，如果不存在则返回null
     */
    @Select("SELECT balance, available_balance, created_at " +
            "FROM account_values_daily " +
            "WHERE model_id = #{modelId} " +
            "AND created_at >= #{todayStart} " +
            "ORDER BY created_at DESC " +
            "LIMIT 1")
    Map<String, Object> selectTodayAccountValue(@Param("modelId") String modelId, 
                                                @Param("todayStart") LocalDateTime todayStart);

    /**
     * 检查模型是否有任何记录
     * 
     * @param modelId 模型ID（UUID格式）
     * @return 记录数量
     */
    @Select("SELECT COUNT(*) FROM account_values_daily WHERE model_id = #{modelId}")
    Long countByModelId(@Param("modelId") String modelId);

}
