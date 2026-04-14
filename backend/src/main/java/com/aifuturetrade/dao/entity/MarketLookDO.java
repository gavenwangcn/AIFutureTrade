package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 实时盯盘任务表 market_look
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("market_look")
public class MarketLookDO implements Serializable {

    private static final long serialVersionUID = 1L;

    public static final String STATUS_RUNNING = "RUNNING";
    public static final String STATUS_ENDED = "ENDED";

    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    private String symbol;

    @TableField("strategy_id")
    private String strategyId;

    @TableField("strategy_name")
    private String strategyName;

    @TableField("execution_status")
    private String executionStatus;

    @TableField("signal_result")
    private String signalResult;

    @TableField("started_at")
    private LocalDateTime startedAt;

    @TableField("ended_at")
    private LocalDateTime endedAt;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;
}
