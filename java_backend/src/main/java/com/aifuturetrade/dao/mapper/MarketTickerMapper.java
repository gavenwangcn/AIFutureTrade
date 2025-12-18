package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.MarketTickerDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：市场Ticker数据
 * 对应表名：24_market_tickers
 */
@Mapper
public interface MarketTickerMapper extends BaseMapper<MarketTickerDO> {

    /**
     * 从 24_market_tickers 表获取涨幅榜数据
     * @param limit 返回的记录数限制
     * @return 涨幅榜数据列表，按 price_change_percent 降序排列
     */
    @Select("SELECT " +
            "`symbol`, `price_change_percent`, `last_price`, `quote_volume`, " +
            "`event_time`, `side` " +
            "FROM `24_market_tickers` " +
            "WHERE `price_change_percent` IS NOT NULL " +
            "AND `price_change_percent` > 0 " +
            "ORDER BY `price_change_percent` DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectGainersFromTickers(@Param("limit") Integer limit);

    /**
     * 从 24_market_tickers 表获取跌幅榜数据
     * @param limit 返回的记录数限制
     * @return 跌幅榜数据列表，按 price_change_percent 绝对值降序排列
     */
    @Select("SELECT " +
            "`symbol`, `price_change_percent`, `last_price`, `quote_volume`, " +
            "`event_time`, `side` " +
            "FROM `24_market_tickers` " +
            "WHERE `price_change_percent` IS NOT NULL " +
            "AND `price_change_percent` < 0 " +
            "ORDER BY ABS(`price_change_percent`) DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectLosersFromTickers(@Param("limit") Integer limit);
}

