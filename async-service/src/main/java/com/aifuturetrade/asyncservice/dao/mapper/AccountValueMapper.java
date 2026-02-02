package com.aifuturetrade.asyncservice.dao.mapper;

import com.aifuturetrade.asyncservice.entity.AccountValueDO;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * Mapper接口：账户价值
 * 对应表名：account_values
 */
@Mapper
public interface AccountValueMapper extends BaseMapper<AccountValueDO> {

    /**
     * 查询指定模型的账户价值（最新记录）
     */
    @Select("SELECT * FROM account_values WHERE model_id = #{modelId} AND account_alias = #{accountAlias} ORDER BY timestamp DESC LIMIT 1")
    AccountValueDO selectLatestByModelAndAlias(@Param("modelId") String modelId, @Param("accountAlias") String accountAlias);

    /**
     * 更新指定ID的账户价值记录
     */
    @Update("UPDATE account_values SET balance = #{balance}, available_balance = #{availableBalance}, " +
            "cross_wallet_balance = #{crossWalletBalance}, cross_pnl = #{crossPnl}, cross_un_pnl = #{crossUnPnl}, " +
            "timestamp = #{timestamp} WHERE id = #{id}")
    int updateAccountValueById(@Param("id") String id,
                              @Param("balance") Double balance,
                              @Param("availableBalance") Double availableBalance,
                              @Param("crossWalletBalance") Double crossWalletBalance,
                              @Param("crossPnl") Double crossPnl,
                              @Param("crossUnPnl") Double crossUnPnl,
                              @Param("timestamp") java.time.LocalDateTime timestamp);
}
