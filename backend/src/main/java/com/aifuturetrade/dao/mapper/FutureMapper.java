package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.FutureDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：合约配置
 * 对应表名：futures
 */
@Mapper
public interface FutureMapper extends BaseMapper<FutureDO> {

    /**
     * 查询所有合约配置
     * @return 合约配置列表
     */
    @Select("select * from futures order by sort_order asc, id asc")
    List<FutureDO> selectAllFutures();

    /**
     * 根据ID查询合约配置
     * @param id 合约ID（UUID格式）
     * @return 合约配置
     */
    @Select("select * from futures where id = #{id}")
    FutureDO selectFutureById(String id);

    /**
     * 获取所有合约符号列表
     * @return 合约符号列表
     */
    @Select("select symbol from futures order by sort_order asc")
    List<String> selectAllSymbols();

}