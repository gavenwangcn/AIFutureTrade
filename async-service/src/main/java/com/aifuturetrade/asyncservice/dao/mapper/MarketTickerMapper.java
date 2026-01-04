package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.ExistingSymbolData;
import com.aifuturetrade.asyncservice.entity.MarketTickerDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Mapper接口：市场Ticker数据
 * 对应表名：24_market_tickers
 * 
 * 扩展了backend的MarketTickerMapper，添加异步服务需要的特殊方法
 */
@Mapper
public interface MarketTickerMapper extends BaseMapper<MarketTickerDO> {

    /**
     * 批量插入或更新ticker数据（使用ON DUPLICATE KEY UPDATE）
     * 注意：此方法需要在XML中实现，这里仅作为接口定义
     * 
     * 参考Python版本的upsert_market_tickers实现：
     * - 只处理USDT交易对
     * - 查询现有数据并计算price_change等字段
     * - 在ON DUPLICATE KEY UPDATE中不更新open_price和update_price_date
     */
    void batchUpsertTickers(@Param("tickers") List<MarketTickerDO> tickers);
    
    /**
     * 查询数据库中已存在交易对的最新数据
     * 参考Python版本的get_existing_symbol_data实现
     * 
     * @param symbols 交易对符号列表
     * @return 包含open_price、last_price、update_price_date的数据列表
     */
    @org.apache.ibatis.annotations.Results({
        @org.apache.ibatis.annotations.Result(property = "symbol", column = "symbol"),
        @org.apache.ibatis.annotations.Result(property = "openPrice", column = "open_price"),
        @org.apache.ibatis.annotations.Result(property = "lastPrice", column = "last_price"),
        @org.apache.ibatis.annotations.Result(property = "updatePriceDate", column = "update_price_date")
    })
    @Select("<script>" +
            "SELECT `symbol`, `open_price`, `last_price`, `update_price_date` " +
            "FROM `24_market_tickers` " +
            "WHERE `symbol` IN " +
            "<foreach collection='symbols' item='symbol' open='(' separator=',' close=')'>" +
            "#{symbol}" +
            "</foreach>" +
            "</script>")
    List<ExistingSymbolData> getExistingSymbolData(@Param("symbols") List<String> symbols);

    /**
     * 查询需要刷新价格的symbol列表
     * 条件：update_price_date为空或超过1小时未更新
     * 
     * @param utc8Time UTC+8时间，用于计算1小时前的时间
     * @return symbol列表
     */
    @Select("SELECT DISTINCT `symbol` " +
            "FROM `24_market_tickers` " +
            "WHERE `update_price_date` IS NULL " +
            "   OR `update_price_date` < DATE_SUB(#{utc8Time}, INTERVAL 1 HOUR) " +
            "ORDER BY `symbol`")
    List<String> selectSymbolsNeedingPriceRefresh(@Param("utc8Time") LocalDateTime utc8Time);

    /**
     * 更新symbol的开盘价和更新日期
     * 
     * 参考Python版本的update_open_price_batch实现：
     * - 使用当前UTC+8时间作为update_price_date（忽略传入的updateDate参数）
     * 
     * @param symbol 交易对符号
     * @param openPrice 开盘价
     * @param updateDate 更新日期（此参数会被忽略，方法内部会使用当前UTC+8时间）
     * @return 更新的记录数
     */
    @Update("UPDATE `24_market_tickers` " +
            "SET `open_price` = #{openPrice}, " +
            "    `update_price_date` = CONVERT_TZ(NOW(), @@session.time_zone, '+08:00') " +
            "WHERE `symbol` = #{symbol}")
    int updateOpenPrice(@Param("symbol") String symbol, 
                       @Param("openPrice") Double openPrice,
                       @Param("updateDate") LocalDateTime updateDate);

    /**
     * 统计需要删除的过期ticker记录数量
     * 
     * @param cutoffDate 截止日期
     * @return 记录数量
     */
    @Select("SELECT COUNT(*) " +
            "FROM `24_market_tickers` " +
            "WHERE `ingestion_time` < #{cutoffDate}")
    Long countOldTickers(@Param("cutoffDate") LocalDateTime cutoffDate);

    /**
     * 删除过期的ticker记录
     * 
     * @param cutoffDate 截止日期
     * @return 删除的记录数
     */
    @Update("DELETE FROM `24_market_tickers` " +
            "WHERE `ingestion_time` < #{cutoffDate}")
    int deleteOldTickers(@Param("cutoffDate") LocalDateTime cutoffDate);
}


