package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;

/**
 * 业务逻辑接口：策略
 */
public interface StrategyService {

    /**
     * 查询所有策略
     * @return 策略列表
     */
    List<StrategyDTO> getAllStrategies();

    /**
     * 根据ID查询策略
     * @param id 策略ID
     * @return 策略
     */
    StrategyDTO getStrategyById(String id);

    /**
     * 根据条件查询策略（支持名称和类型筛选）
     * @param name 策略名称（模糊查询）
     * @param type 策略类型
     * @return 策略列表
     */
    List<StrategyDTO> getStrategiesByCondition(String name, String type);

    /**
     * 分页查询策略
     * @param pageRequest 分页请求
     * @param name 策略名称（可选）
     * @param type 策略类型（可选）
     * @return 分页查询结果
     */
    PageResult<StrategyDTO> getStrategiesByPage(PageRequest pageRequest, String name, String type);

    /**
     * 添加策略
     * @param strategyDTO 策略信息
     * @return 新增的策略
     */
    StrategyDTO addStrategy(StrategyDTO strategyDTO);

    /**
     * 更新策略
     * @param strategyDTO 策略信息
     * @return 更新后的策略
     */
    StrategyDTO updateStrategy(StrategyDTO strategyDTO);

    /**
     * 删除策略
     * @param id 策略ID
     * @return 是否删除成功
     */
    Boolean deleteStrategy(String id);

}

