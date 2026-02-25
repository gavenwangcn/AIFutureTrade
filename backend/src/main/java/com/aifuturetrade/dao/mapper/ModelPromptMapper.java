package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.ModelPromptDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Mapper接口：模型提示词配置
 */
@Mapper
public interface ModelPromptMapper extends BaseMapper<ModelPromptDO> {

    /**
     * 根据模型ID删除模型提示词配置
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM model_prompts WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

