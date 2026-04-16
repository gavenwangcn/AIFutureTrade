package com.aifuturetrade.service.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 盯盘任务 API 传输对象（字段与 DB 一致，JSON 使用 snake_case）
 */
@Data
public class MarketLookDTO implements Serializable {

    private static final long serialVersionUID = 1L;

    private String id;

    private String symbol;

    @JsonProperty("strategy_id")
    @JsonAlias({"strategyId"})
    private String strategyId;

    @JsonProperty("strategy_name")
    @JsonAlias({"strategyName"})
    private String strategyName;

    /** RUNNING | SENDING | ENDED */
    @JsonProperty("execution_status")
    @JsonAlias({"executionStatus"})
    private String executionStatus;

    @JsonProperty("signal_result")
    @JsonAlias({"signalResult"})
    private String signalResult;

    /** 任务详情摘要 */
    @JsonProperty("detail_summary")
    @JsonAlias({"detailSummary"})
    private String detailSummary;

    /** 任务结束说明（非策略信号类：正常/异常/超时等） */
    @JsonProperty("end_log")
    @JsonAlias({"endLog"})
    private String endLog;

    /** 执行开始时间（必填） */
    @JsonProperty("started_at")
    @JsonAlias({"startedAt"})
    private LocalDateTime startedAt;

    /** 执行结束时间（必填）；RUNNING 时为计划截止时间（盯盘引擎据此判断超时），历史数据可能仍为 2099 占位 */
    @JsonProperty("ended_at")
    @JsonAlias({"endedAt"})
    private LocalDateTime endedAt;

    @JsonProperty("created_at")
    @JsonAlias({"createdAt"})
    private LocalDateTime createdAt;

    @JsonProperty("updated_at")
    @JsonAlias({"updatedAt"})
    private LocalDateTime updatedAt;
}
