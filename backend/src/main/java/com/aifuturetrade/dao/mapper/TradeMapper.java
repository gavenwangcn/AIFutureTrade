package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.TradeDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
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
     * @param modelId 模型ID（UUID格式）
     * @param limit 限制数量
     * @return 交易记录列表
     */
    @Select("select * from trades where model_id = #{modelId} order by timestamp desc limit #{limit}")
    List<TradeDO> selectTradesByModelId(@Param("modelId") String modelId, @Param("limit") Integer limit);
    
    /**
     * 根据模型ID统计交易记录总数
     * @param modelId 模型ID（UUID格式）
     * @return 交易记录总数
     */
    @Select("select count(*) from trades where model_id = #{modelId}")
    Long countTradesByModelId(@Param("modelId") String modelId);

    /**
     * 根据模型ID删除交易记录
     * @param modelId 模型ID（UUID格式）
     * @return 删除的记录数
     */
    @Delete("DELETE FROM trades WHERE model_id = #{modelId}")
    int deleteByModelId(@Param("modelId") String modelId);

}