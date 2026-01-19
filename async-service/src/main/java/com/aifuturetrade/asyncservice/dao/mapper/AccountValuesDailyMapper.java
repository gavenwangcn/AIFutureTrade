package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.AccountValuesDailyDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Mapper接口：账户每日价值
 * 对应表名：account_values_daily
 */
@Mapper
public interface AccountValuesDailyMapper extends BaseMapper<AccountValuesDailyDO> {

    /**
     * 插入每日账户价值记录
     * @param id 记录ID
     * @param modelId 模型ID
     * @param balance 账户总值
     * @param availableBalance 可用现金
     */
    @Insert("INSERT INTO account_values_daily (id, model_id, balance, available_balance, created_at) " +
            "VALUES (#{id}, #{modelId}, #{balance}, #{availableBalance}, NOW())")
    void insertDailyAccountValue(@Param("id") String id, 
                                 @Param("modelId") String modelId,
                                 @Param("balance") Double balance,
                                 @Param("availableBalance") Double availableBalance);
}
