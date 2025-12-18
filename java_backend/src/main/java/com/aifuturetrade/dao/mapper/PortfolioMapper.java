package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.PortfolioDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

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
    List<Map<String, Object>> selectPortfoliosByModelId(@Param("modelId") Integer modelId);

    /**
     * 根据模型ID和交易对查询持仓
     */
    PortfolioDO selectByModelIdAndSymbol(@Param("modelId") Integer modelId, @Param("symbol") String symbol, @Param("positionSide") String positionSide);

}

