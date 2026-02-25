package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.AccountValueHistoryDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * Mapper接口：账户价值历史
 * 对应表名：account_value_historys
 */
@Mapper
public interface AccountValueHistoryMapper extends BaseMapper<AccountValueHistoryDO> {
}
