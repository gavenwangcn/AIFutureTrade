package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.ModelStrategyDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：模型关联策略
 * 对应表名：model_strategy
 */
@Mapper
public interface ModelStrategyMapper extends BaseMapper<ModelStrategyDO> {

    /**
     * 查询所有模型策略关联
     * @return 模型策略关联列表
     */
    @Select("select * from model_strategy order by created_at desc")
    List<ModelStrategyDO> selectAllModelStrategies();

    /**
     * 根据ID查询模型策略关联
     * @param id 关联ID
     * @return 模型策略关联
     */
    @Select("select * from model_strategy where id = #{id}")
    ModelStrategyDO selectModelStrategyById(String id);

    /**
     * 根据模型ID查询模型策略关联
     * @param modelId 模型ID
     * @return 模型策略关联列表
     */
    @Select("select * from model_strategy where model_id = #{modelId} order by created_at desc")
    List<ModelStrategyDO> selectModelStrategiesByModelId(String modelId);

    /**
     * 根据模型ID查询模型策略关联（包含策略详细信息）
     * @param modelId 模型ID
     * @return 模型策略关联列表（包含策略名称和类型）
     */
    @Select("SELECT ms.*, s.name as strategy_name, s.type as strategy_type " +
            "FROM model_strategy ms " +
            "INNER JOIN strategys s ON ms.strategy_id = s.id " +
            "WHERE ms.model_id = #{modelId} " +
            "ORDER BY ms.priority DESC, ms.created_at ASC")
    List<Map<String, Object>> selectModelStrategiesWithStrategyInfoByModelId(@Param("modelId") String modelId);

    /**
     * 根据策略ID查询模型策略关联
     * @param strategyId 策略ID
     * @return 模型策略关联列表
     */
    @Select("select * from model_strategy where strategy_id = #{strategyId} order by created_at desc")
    List<ModelStrategyDO> selectModelStrategiesByStrategyId(String strategyId);

    /**
     * 根据模型ID和类型查询模型策略关联
     * @param modelId 模型ID
     * @param type 策略类型
     * @return 模型策略关联列表
     */
    @Select("select * from model_strategy where model_id = #{modelId} and type = #{type} order by created_at desc")
    List<ModelStrategyDO> selectModelStrategiesByModelIdAndType(@Param("modelId") String modelId, @Param("type") String type);

}

