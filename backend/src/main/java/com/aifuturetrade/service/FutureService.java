package com.aifuturetrade.service;

import com.aifuturetrade.service.dto.FutureDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;

import java.util.List;

/**
 * 业务逻辑接口：合约配置
 */
public interface FutureService {

    /**
     * 查询所有合约配置
     * @return 合约配置列表
     */
    List<FutureDTO> getAllFutures();

    /**
     * 根据ID查询合约配置
     * @param id 合约ID
     * @return 合约配置
     */
    FutureDTO getFutureById(String id);

    /**
     * 添加合约配置
     * @param futureDTO 合约配置信息
     * @return 新增的合约配置
     */
    FutureDTO addFuture(FutureDTO futureDTO);

    /**
     * 更新合约配置
     * @param futureDTO 合约配置信息
     * @return 更新后的合约配置
     */
    FutureDTO updateFuture(FutureDTO futureDTO);

    /**
     * 删除合约配置
     * @param id 合约ID（UUID格式）
     * @return 是否删除成功
     */
    Boolean deleteFuture(String id);

    /**
     * 分页查询合约配置
     * @param pageRequest 分页请求
     * @return 分页查询结果
     */
    PageResult<FutureDTO> getFuturesByPage(PageRequest pageRequest);

    /**
     * 获取所有合约符号列表
     * @return 合约符号列表
     */
    List<String> getTrackedSymbols();

}