package com.aifuturetrade.dao.mapper;

import com.aifuturetrade.dao.entity.AccountAssetDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * Mapper接口：账户资产
 */
@Mapper
public interface AccountAssetMapper extends BaseMapper<AccountAssetDO> {

    /**
     * 查询所有账户信息
     * @return 账户信息列表
     */
    @Select("SELECT " +
            "account_alias, account_name, api_key, api_secret, " +
            "total_initial_margin, total_maint_margin, total_wallet_balance, " +
            "total_unrealized_profit, total_margin_balance, total_position_initial_margin, " +
            "total_open_order_initial_margin, total_cross_wallet_balance, total_cross_un_pnl, " +
            "available_balance, max_withdraw_amount, update_time, created_at " +
            "FROM account_asset " +
            "ORDER BY created_at DESC")
    List<Map<String, Object>> selectAllAccounts();

}

