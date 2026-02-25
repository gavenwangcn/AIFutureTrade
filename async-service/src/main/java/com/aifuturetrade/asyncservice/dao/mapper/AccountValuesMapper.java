package com.aifuturetrade.asyncservice.dao.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：账户价值（用于查询balance和available_balance）
 * 对应表名：account_values
 */
@Mapper
public interface AccountValuesMapper {
    
    /**
     * 查询所有模型的账户价值
     * @return 账户价值列表，包含model_id, balance, available_balance
     */
    @Select("SELECT model_id, balance, available_balance FROM account_values")
    List<Map<String, Object>> selectAllAccountValues();
    
    /**
     * 根据模型ID查询账户价值
     * @param modelId 模型ID
     * @return 账户价值，包含balance和available_balance
     */
    @Select("SELECT model_id, balance, available_balance FROM account_values WHERE model_id = #{modelId}")
    Map<String, Object> selectAccountValueByModelId(@Param("modelId") String modelId);
}
