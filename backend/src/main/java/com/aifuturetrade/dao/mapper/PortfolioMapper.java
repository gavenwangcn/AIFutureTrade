package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.PortfolioDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：投资组合持仓
 */
@Mapper
public interface PortfolioMapper extends BaseMapper<PortfolioDO> {

    /**
     * 根据模型ID查询持仓列表
     */
    List<Map<String, Object>> selectPortfoliosByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID和交易对查询持仓
     */
    @Select("SELECT * FROM portfolios WHERE model_id = #{modelId} AND symbol = #{symbol} LIMIT 1")
    PortfolioDO selectByModelIdAndSymbol(@Param("modelId") String modelId, @Param("symbol") String symbol, @Param("positionSide") String positionSide);

    /**
     * 根据模型ID删除持仓记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM portfolios WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}

