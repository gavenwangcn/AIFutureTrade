package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：模型关联策略
 * 对应表名：model_strategy
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("model_strategy")
public class ModelStrategyDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型ID
     */
    private String modelId;

    /**
     * 策略ID
     */
    private String strategyId;

    /**
     * 策略类型（buy-买，sell-卖）
     */
    private String type;

    /**
     * 策略优先级，数字越大优先级越高
     */
    private Integer priority;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

}

