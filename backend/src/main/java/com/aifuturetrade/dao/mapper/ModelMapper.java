package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.ModelDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：交易模型
 * 对应表名：models
 */
@Mapper
public interface ModelMapper extends BaseMapper<ModelDO> {

    /**
     * 查询所有交易模型
     * @return 交易模型列表
     */
    @Select("select * from models order by id asc")
    List<ModelDO> selectAllModels();

    /**
     * 根据ID查询交易模型
     * @param id 模型ID（UUID格式）
     * @return 交易模型
     */
    @Select("select * from models where id = #{id}")
    ModelDO selectModelById(String id);

    /**
     * 检查模型是否启用自动买入
     * @param modelId 模型ID（UUID格式）
     * @return 1：启用，0：未启用
     */
    @Select("select auto_buy_enabled from models where id = #{modelId}")
    Boolean isModelAutoBuyEnabled(String modelId);

    /**
     * 检查模型是否启用自动卖出
     * @param modelId 模型ID（UUID格式）
     * @return 1：启用，0：未启用
     */
    @Select("select auto_sell_enabled from models where id = #{modelId}")
    Boolean isModelAutoSellEnabled(String modelId);

}