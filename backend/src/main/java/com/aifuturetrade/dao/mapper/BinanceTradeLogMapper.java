package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.BinanceTradeLogDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Mapper接口：币安交易日志
 * 对应表名：binance_trade_logs
 */
@Mapper
public interface BinanceTradeLogMapper extends BaseMapper<BinanceTradeLogDO> {

    /**
     * 根据模型ID删除币安交易日志记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM binance_trade_logs WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

