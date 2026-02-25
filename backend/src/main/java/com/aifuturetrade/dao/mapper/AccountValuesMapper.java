package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AccountValuesDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Mapper接口：账户价值
 */
@Mapper
public interface AccountValuesMapper extends BaseMapper<AccountValuesDO> {

    /**
     * 根据模型ID删除账户价值记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM account_values WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

