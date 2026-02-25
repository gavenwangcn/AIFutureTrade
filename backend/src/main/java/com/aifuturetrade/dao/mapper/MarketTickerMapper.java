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
            "`symbol`, `price_change_percent`, `last_price`, `quote_volume`, `base_volume`, " +
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
            "`symbol`, `price_change_percent`, `last_price`, `quote_volume`, `base_volume`, " +
            "`event_time`, `side` " +
            "FROM `24_market_tickers` " +
            "WHERE `price_change_percent` IS NOT NULL " +
            "AND `price_change_percent` < 0 " +
            "ORDER BY ABS(`price_change_percent`) DESC " +
            "LIMIT #{limit}")
    List<Map<String, Object>> selectLosersFromTickers(@Param("limit") Integer limit);

    /**
     * 从 24_market_tickers 表根据symbol列表获取ticker数据
     * 每个symbol只返回最新的一条记录（按event_time降序）
     * @param symbols 交易对符号列表
     * @return ticker数据列表，包含 price_change_percent 和 quote_volume
     */
    @Select("<script>" +
            "SELECT t1.`symbol`, t1.`price_change_percent`, t1.`quote_volume` " +
            "FROM `24_market_tickers` t1 " +
            "INNER JOIN (" +
            "  SELECT `symbol`, MAX(`event_time`) as max_event_time " +
            "  FROM `24_market_tickers` " +
            "  WHERE `symbol` IN " +
            "  <foreach collection='symbols' item='symbol' open='(' separator=',' close=')'>" +
            "    #{symbol}" +
            "  </foreach>" +
            "  GROUP BY `symbol`" +
            ") t2 ON t1.`symbol` = t2.`symbol` AND t1.`event_time` = t2.max_event_time" +
            "</script>")
    List<Map<String, Object>> selectTickersBySymbols(@Param("symbols") List<String> symbols);
}

