package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.TradeDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * Mapper接口：交易记录
 * 对应表名：trades
 */
@Mapper
public interface TradeMapper extends BaseMapper<TradeDO> {
}
