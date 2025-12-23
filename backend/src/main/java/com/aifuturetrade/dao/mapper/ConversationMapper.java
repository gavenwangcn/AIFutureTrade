package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.ConversationDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：AI对话记录
 * 对应表名：conversations
 */
@Mapper
public interface ConversationMapper extends BaseMapper<ConversationDO> {

    /**
     * 根据模型ID查询对话记录，按照时间倒序排列
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 对话记录列表
     */
    @Select("select * from conversations where model_id = #{modelId} order by timestamp desc limit #{limit}")
    List<ConversationDO> selectConversationsByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);

    /**
     * 根据模型ID删除对话记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM conversations WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}