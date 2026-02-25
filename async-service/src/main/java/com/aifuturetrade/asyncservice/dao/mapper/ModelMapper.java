package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.ModelDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

/**
 * Mapper接口：交易模型（用于自动平仓服务）
 * 对应表名：models
 */
@Mapper
public interface ModelMapper extends BaseMapper<ModelDO> {

    /**
     * 根据ID查询交易模型
     * @param id 模型ID（UUID格式）
     * @return 交易模型
     */
    @Select("SELECT * FROM models WHERE id = #{id}")
    ModelDO selectModelById(String id);
}

