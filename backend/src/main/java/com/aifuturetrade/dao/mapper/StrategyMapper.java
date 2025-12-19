package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.StrategyDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：策略
 * 对应表名：strategys
 */
@Mapper
public interface StrategyMapper extends BaseMapper<StrategyDO> {

    /**
     * 查询所有策略
     * @return 策略列表
     */
    @Select("select * from strategys order by created_at desc")
    List<StrategyDO> selectAllStrategies();

    /**
     * 根据ID查询策略
     * @param id 策略ID
     * @return 策略
     */
    @Select("select * from strategys where id = #{id}")
    StrategyDO selectStrategyById(String id);

    /**
     * 根据名称和类型查询策略
     * 注意：此方法在 Service 层使用 LambdaQueryWrapper 实现动态查询
     * @param name 策略名称（模糊查询）
     * @param type 策略类型
     * @return 策略列表
     */
    List<StrategyDO> selectStrategiesByCondition(String name, String type);

}

