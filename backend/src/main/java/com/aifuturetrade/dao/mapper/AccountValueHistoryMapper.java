package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AccountValueHistoryDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：账户价值历史记录
 */
@Mapper
public interface AccountValueHistoryMapper extends BaseMapper<AccountValueHistoryDO> {

    /**
     * 根据模型ID查询账户价值历史
     */
    List<Map<String, Object>> selectHistoryByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);

    /**
     * 查询聚合账户价值历史（所有模型）
     */
    List<Map<String, Object>> selectAggregatedHistory(@Param("limit") Integer limit);

    /**
     * 查询多模型图表数据
     */
    List<Map<String, Object>> selectMultiModelChartData(@Param("limit") Integer limit);

}

