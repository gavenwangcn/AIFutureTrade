package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.LlmApiErrorDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：LLM API错误记录
 * 对应表名：llm_api_errors
 */
@Mapper
public interface LlmApiErrorMapper extends BaseMapper<LlmApiErrorDO> {

    /**
     * 根据模型ID查询API错误记录，按照时间倒序排列
     * @param modelId 模型ID
     * @param limit 限制数量
     * @return API错误记录列表
     */
    @Select("select * from llm_api_errors where model_id = #{modelId} order by created_at desc limit #{limit}")
    List<LlmApiErrorDO> selectLlmApiErrorsByModelId(Integer modelId, Integer limit);

}