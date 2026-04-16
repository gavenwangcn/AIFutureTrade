package com.aifuturetrade.service;

/**
 * 盯盘任务删除结果：除「已校验库中无此行」外均视为未成功删除。
 */
public enum MarketLookDeleteOutcome {

    /** 主键不存在 */
    NOT_FOUND,

    /** 已执行 delete 且再次 select 确认行已不存在 */
    VERIFIED_REMOVED,

    /** delete 返回受影响行数为 0（异常） */
    NO_ROWS_DELETED,

    /** delete 声称成功但行仍可被查到（数据不一致，需排查） */
    VERIFY_FAILED
}
