package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;
import java.util.Map;

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
     * 根据条件查询策略（支持名称、内容和类型筛选）
     * @param keyword 搜索关键词（匹配策略名称或策略内容）
     * @param type 策略类型
     * @return 策略列表
     */
    List<StrategyDTO> getStrategiesByKeyword(String keyword, String type);

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

    /**
     * 按策略 ID 使用 AI 重新生成策略代码；可选覆盖 strategy_context / validate_symbol（盯盘）。
     * 仅当代码测试通过时写入数据库（与新建策略校验一致）。
     *
     * @param strategyId        策略 UUID
     * @param providerId        AI 提供方 ID
     * @param modelName         模型名
     * @param strategyContext   若非空则替换后再生成；否则使用库中现有 strategy_context（须非空）
     * @param validateSymbol    盯盘可选覆盖 validate_symbol；否则用库中值
     * @param strategyName      测试用名称，可选
     * @param persist           为 true（默认）且测试通过时更新库；为 false 时只返回生成结果不保存
     * @return id、strategyCode、testPassed、testResult、persisted、message 等
     */
    Map<String, Object> regenerateStrategyCode(
            String strategyId,
            String providerId,
            String modelName,
            String strategyContext,
            String validateSymbol,
            String strategyName,
            Boolean persist);

}

