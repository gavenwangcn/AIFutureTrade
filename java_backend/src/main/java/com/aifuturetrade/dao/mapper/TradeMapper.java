package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.TradeDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：交易记录
 * 对应表名：trades
 */
@Mapper
public interface TradeMapper extends BaseMapper<TradeDO> {

    /**
     * 根据模型ID查询交易记录，按照时间倒序排列
     * @param modelId 模型ID
     * @param limit 限制数量
     * @return 交易记录列表
     */
    @Select("select * from trades where model_id = #{modelId} order by timestamp desc limit #{limit}")
    List<TradeDO> selectTradesByModelId(Integer modelId, Integer limit);

}