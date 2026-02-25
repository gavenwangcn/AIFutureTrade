package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.PortfolioDO;
import com.aifuturetrade.asyncservice.entity.PortfolioWithModelInfo;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Result;
import org.apache.ibatis.annotations.Results;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * Mapper接口：投资组合持仓（用于自动平仓服务）
 * 对应表名：portfolios
 */
@Mapper
public interface PortfolioMapper extends BaseMapper<PortfolioDO> {

    /**
     * 查询所有持仓记录（用于自动平仓服务）
     * 只查询持仓数量不为0的记录
     * 
     * @return 持仓记录列表
     */
    @Results({
        @Result(property = "modelId", column = "model_id"),
        @Result(property = "symbol", column = "symbol"),
        @Result(property = "positionSide", column = "position_side"),
        @Result(property = "positionAmt", column = "position_amt"),
        @Result(property = "avgPrice", column = "avg_price"),
        @Result(property = "initialMargin", column = "initial_margin"),
        @Result(property = "autoClosePercent", column = "auto_close_percent"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "apiSecret", column = "api_secret")
    })
    @Select("SELECT p.model_id, p.symbol, p.position_side, p.position_amt, p.avg_price, " +
            "       p.initial_margin, m.auto_close_percent, m.api_key, m.api_secret " +
            "FROM portfolios p " +
            "INNER JOIN models m ON p.model_id = m.id " +
            "WHERE p.position_amt != 0 " +
            "  AND m.auto_close_percent IS NOT NULL " +
            "  AND m.auto_close_percent > 0 " +
            "ORDER BY p.model_id, p.symbol")
    List<PortfolioWithModelInfo> selectAllActivePositions();

    /**
     * 删除持仓记录（平仓后使用）
     * 
     * @param modelId 模型ID
     * @param symbol 交易对符号
     * @param positionSide 持仓方向（LONG/SHORT）
     * @return 删除的记录数
     */
    @org.apache.ibatis.annotations.Delete("DELETE FROM portfolios " +
            "WHERE model_id = #{modelId} AND symbol = #{symbol} AND position_side = #{positionSide}")
    int deletePosition(@Param("modelId") String modelId, 
                      @Param("symbol") String symbol, 
                      @Param("positionSide") String positionSide);

    /**
     * 查询指定模型的持仓记录
     */
    @Select("SELECT * FROM portfolios WHERE model_id = #{modelId} AND symbol = #{symbol} AND position_side = #{positionSide}")
    PortfolioDO selectPosition(@Param("modelId") String modelId, 
                               @Param("symbol") String symbol, 
                               @Param("positionSide") String positionSide);

    /**
     * 更新持仓数量
     */
    @org.apache.ibatis.annotations.Update("UPDATE portfolios SET position_amt = #{positionAmt}, updated_at = NOW() " +
            "WHERE model_id = #{modelId} AND symbol = #{symbol} AND position_side = #{positionSide}")
    int updatePositionAmt(@Param("modelId") String modelId,
                          @Param("symbol") String symbol,
                          @Param("positionSide") String positionSide,
                          @Param("positionAmt") Double positionAmt);
}

