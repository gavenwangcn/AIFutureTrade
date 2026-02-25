package com.aifuturetrade.service;

import java.util.List;
import java.util.Map;

/**
 * 账户管理服务接口
 */
public interface AccountService {

    /**
     * 查询所有账户信息
     */
    List<Map<String, Object>> getAllAccounts();

    /**
     * 添加新账户
     */
    Map<String, Object> addAccount(Map<String, Object> accountData);

    /**
     * 删除账户
     */
    Map<String, Object> deleteAccount(String accountAlias);

}

