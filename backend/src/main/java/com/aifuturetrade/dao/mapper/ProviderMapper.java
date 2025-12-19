package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.ProviderDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：API提供方
 * 对应表名：providers
 */
@Mapper
public interface ProviderMapper extends BaseMapper<ProviderDO> {

    /**
     * 查询所有API提供方
     * @return API提供方列表
     */
    @Select("select * from providers order by id asc")
    List<ProviderDO> selectAllProviders();

    /**
     * 根据ID查询API提供方
     * @param id 提供方ID
     * @return API提供方
     */
    @Select("select * from providers where id = #{id}")
    ProviderDO selectProviderById(Integer id);

}