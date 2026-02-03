package com.aifuturetrade.service.impl;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.dao.entity.AlgoOrderDO;
import com.aifuturetrade.dao.mapper.AlgoOrderMapper;
import com.aifuturetrade.service.AlgoOrderService;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 条件订单服务实现
 */
@Slf4j
@Service
public class AlgoOrderServiceImpl implements AlgoOrderService {
    
    @Autowired
    private AlgoOrderMapper algoOrderMapper;
    
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    
    @Override
    public PageResult<Map<String, Object>> getAlgoOrdersByPage(String modelId, PageRequest pageRequest) {
        log.debug("[AlgoOrderService] ========== 开始获取条件订单（分页） ==========");
        log.debug("[AlgoOrderService] modelId: {}, pageNum: {}, pageSize: {}", modelId, pageRequest.getPageNum(), pageRequest.getPageSize());
        
        try {
            // 设置默认值
            Integer pageNum = pageRequest.getPageNum() != null && pageRequest.getPageNum() > 0 ? pageRequest.getPageNum() : 1;
            Integer pageSize = pageRequest.getPageSize() != null && pageRequest.getPageSize() > 0 ? pageRequest.getPageSize() : 10;
            
            // 查询总数
            Long total = algoOrderMapper.countAlgoOrdersByModelId(modelId);
            log.debug("[AlgoOrderService] 条件订单总数: {}", total);
            
            // 使用MyBatis-Plus的Page进行分页查询
            Page<AlgoOrderDO> page = new Page<>(pageNum, pageSize);
            QueryWrapper<AlgoOrderDO> queryWrapper = new QueryWrapper<>();
            queryWrapper.eq("model_id", modelId);
            queryWrapper.orderByDesc("created_at");
            Page<AlgoOrderDO> algoOrderDOPage = algoOrderMapper.selectPage(page, queryWrapper);
            
            List<AlgoOrderDO> algoOrderDOList = algoOrderDOPage.getRecords();
            log.debug("[AlgoOrderService] 从数据库查询到 {} 条条件订单（第{}页，每页{}条）", algoOrderDOList.size(), pageNum, pageSize);
            
            List<Map<String, Object>> algoOrders = convertAlgoOrdersToMapList(algoOrderDOList);
            
            log.debug("[AlgoOrderService] 转换完成，共 {} 条条件订单", algoOrders.size());
            log.debug("[AlgoOrderService] ========== 获取条件订单（分页）完成 ==========");
            
            return PageResult.build(algoOrders, total, pageNum, pageSize);
        } catch (Exception e) {
            log.error("[AlgoOrderService] 获取条件订单（分页）失败: {}", e.getMessage(), e);
            return PageResult.build(new ArrayList<>(), 0L, pageRequest.getPageNum(), pageRequest.getPageSize());
        }
    }
    
    /**
     * 将AlgoOrderDO列表转换为Map列表（只包含前端需要的字段）
     */
    private List<Map<String, Object>> convertAlgoOrdersToMapList(List<AlgoOrderDO> algoOrderDOList) {
        List<Map<String, Object>> algoOrders = new ArrayList<>();
        
        for (AlgoOrderDO algoOrderDO : algoOrderDOList) {
            Map<String, Object> algoOrder = new HashMap<>();
            
            // 只包含前端需要的字段：symbol, side, positionSide, quantity, type, algoStatus, price, created_at, error_reason
            algoOrder.put("id", algoOrderDO.getId());
            algoOrder.put("symbol", algoOrderDO.getSymbol());
            algoOrder.put("side", algoOrderDO.getSide());
            algoOrder.put("positionSide", algoOrderDO.getPositionSide());
            algoOrder.put("quantity", algoOrderDO.getQuantity() != null ? algoOrderDO.getQuantity() : 0.0);
            algoOrder.put("type", algoOrderDO.getOrderType()); // 使用orderType作为type
            algoOrder.put("algoStatus", algoOrderDO.getAlgoStatus());
            algoOrder.put("price", algoOrderDO.getPrice() != null ? algoOrderDO.getPrice() : 0.0);
            algoOrder.put("error_reason", algoOrderDO.getErrorReason()); // 添加失败原因字段
            
            // 格式化时间
            if (algoOrderDO.getCreatedAt() != null) {
                algoOrder.put("created_at", algoOrderDO.getCreatedAt().format(DATE_TIME_FORMATTER));
            } else {
                algoOrder.put("created_at", "");
            }
            
            algoOrders.add(algoOrder);
        }
        
        return algoOrders;
    }
}
