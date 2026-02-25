package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.StrategyDecisionDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：策略决策
 * 对应表名：strategy_decisions
 */
@Mapper
public interface StrategyDecisionMapper extends BaseMapper<StrategyDecisionDO> {

    /**
     * 根据模型ID查询策略决策记录，按照时间倒序排列
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 策略决策记录列表
     */
    @Select("SELECT * FROM strategy_decisions WHERE model_id = #{modelId} ORDER BY created_at DESC LIMIT #{limit}")
    List<StrategyDecisionDO> selectDecisionsByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);
    
    /**
     * 根据模型ID统计策略决策记录总数
     * @param modelId 模型ID（UUID格式）
     * @return 策略决策记录总数
     */
    @Select("SELECT COUNT(*) FROM strategy_decisions WHERE model_id = #{modelId}")
    Long countDecisionsByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID删除策略决策记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM strategy_decisions WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

