package com.aifuturetrade.trademcp.tools;

import com.aifuturetrade.trademcp.client.BackendClient;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 盯盘 market_look 与盯盘策略 strategys(type=look)，经 {@link BackendClient} 调用主库 Java backend。
 */
@Component
public class MarketLookTools {

    private static final String SQL_DESC =
            "只读 SELECT，SQL 文本中必须出现表名 market_look（建议 `market_look`）；仅允许 SELECT；"
                    + "使用 ? 占位防注入；params 与 ? 从左到右一一对应。"
                    + " 主要列：id, symbol, strategy_id, strategy_name, execution_status(RUNNING/SENDING/ENDED), "
                    + "signal_result, detail_summary, started_at, ended_at, created_at, updated_at。"
                    + " 示例：SELECT id,symbol,execution_status,started_at,ended_at FROM `market_look` WHERE execution_status=? LIMIT 20";

    private final BackendClient backendClient;

    public MarketLookTools(BackendClient backendClient) {
        this.backendClient = backendClient;
    }

    @McpTool(
            name = "trade_look_market_look_create",
            description = "新建盯盘任务 market_look。成功时响应含 id（UUID）与 data。"
                    + " 必填：symbol（合约如 BTC 或 BTCUSDT）、strategy_id（须为 strategys 中 type=look 的策略 ID）、"
                    + "detail_summary（任务摘要）。"
                    + " 可选：strategy_name、execution_status（默认 RUNNING；创建时仅允许 RUNNING 或 ENDED）、"
                    + "signal_result、started_at/ended_at（ISO 或 yyyy-MM-dd HH:mm:ss；RUNNING 时若省略则服务端默认开始=现在、结束=开始+24h）。"
                    + " 失败时 success=false 与 error 说明。")
    public Map<String, Object> marketLookCreate(
            @McpToolParam(description = "合约符号，如 BTC 或 BTCUSDT", required = true) String symbol,
            @McpToolParam(description = "策略 UUID（strategys.id，且 type 必须为 look）", required = true) String strategyId,
            @McpToolParam(description = "详情摘要，非空字符串", required = true) String detailSummary,
            @McpToolParam(description = "策略名称冗余，可选", required = false) String strategyName,
            @McpToolParam(description = "RUNNING 或 ENDED，默认 RUNNING", required = false) String executionStatus,
            @McpToolParam(description = "信号结果文本或 JSON 字符串，可选", required = false) String signalResult,
            @McpToolParam(description = "开始时间，可选", required = false) String startedAt,
            @McpToolParam(description = "结束/截止时间，可选", required = false) String endedAt) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("symbol", symbol);
        body.put("strategy_id", strategyId);
        body.put("detail_summary", detailSummary);
        if (strategyName != null && !strategyName.isEmpty()) {
            body.put("strategy_name", strategyName);
        }
        if (executionStatus != null && !executionStatus.isEmpty()) {
            body.put("execution_status", executionStatus);
        }
        if (signalResult != null && !signalResult.isEmpty()) {
            body.put("signal_result", signalResult);
        }
        if (startedAt != null && !startedAt.isEmpty()) {
            body.put("started_at", startedAt);
        }
        if (endedAt != null && !endedAt.isEmpty()) {
            body.put("ended_at", endedAt);
        }
        return backendClient.marketLookCreate(body);
    }

    @McpTool(
            name = "trade_look_strategy_create_look",
            description = "新建策略，且 type 固定为盯盘 look。成功时响应含 id 与 message。"
                    + " 必填：name（策略名称）。"
                    + " 若填写 strategy_code，则必须同时提供 validate_symbol（校验用合约如 BTCUSDT），服务端会执行代码校验。"
                    + " 可选：strategy_context（说明/上下文）、strategy_code（Python 策略代码）。"
                    + " type 由本工具固定为 look，无需传入。")
    public Map<String, Object> strategyCreateLook(
            @McpToolParam(description = "策略名称", required = true) String name,
            @McpToolParam(description = "校验合约符号，填写 strategy_code 时必填", required = false) String validateSymbol,
            @McpToolParam(description = "策略说明/上下文，可选", required = false) String strategyContext,
            @McpToolParam(description = "策略代码，可选；有代码时必须 validate_symbol", required = false) String strategyCode) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", name);
        body.put("type", "look");
        if (validateSymbol != null && !validateSymbol.isEmpty()) {
            body.put("validate_symbol", validateSymbol);
        }
        if (strategyContext != null && !strategyContext.isEmpty()) {
            body.put("strategy_context", strategyContext);
        }
        if (strategyCode != null && !strategyCode.isEmpty()) {
            body.put("strategy_code", strategyCode);
        }
        return backendClient.strategyCreate(body);
    }

    @McpTool(
            name = "trade_look_strategy_get_by_id",
            description = "按主键查询策略；用于盯盘时请确认返回的 type 为 look。响应为策略对象字段（id/name/type/validate_symbol/strategy_context/strategy_code 等）。")
    public Map<String, Object> strategyGetById(
            @McpToolParam(description = "strategys.id（UUID）", required = true) String strategyId) {
        return backendClient.strategyGetById(strategyId);
    }

    @McpTool(
            name = "trade_look_strategy_search_look",
            description = "分页查询盯盘类策略：固定 type=look。name 可选，模糊匹配策略名称；不传 name 则不过滤名称。"
                    + " 返回 PageResult：data 为策略列表。")
    public Map<String, Object> strategySearchLook(
            @McpToolParam(description = "页码，从 1 开始，默认 1", required = false) Integer pageNum,
            @McpToolParam(description = "每页条数，默认 50，最大依后端限制", required = false) Integer pageSize,
            @McpToolParam(description = "策略名称关键字，模糊查询，可选", required = false) String name) {
        return backendClient.strategyPageByType(pageNum, pageSize, name, "look");
    }

    @McpTool(
            name = "trade_look_market_look_query_page",
            description = "分页查询盯盘任务。可按运行状态 execution_status（RUNNING/SENDING/ENDED）、symbol（模糊）、strategy_id、"
                    + "started_at/ended_at 时间范围筛选（闭区间）。时间格式：yyyy-MM-dd HH:mm:ss 或 ISO-8601。"
                    + " 返回 PageResult：data 为行列表，total、pageNum、pageSize、totalPages。")
    public Map<String, Object> marketLookQueryPage(
            @McpToolParam(description = "页码，从 1 开始，默认 1", required = false) Integer pageNum,
            @McpToolParam(description = "每页条数，默认 10", required = false) Integer pageSize,
            @McpToolParam(description = "执行状态：RUNNING / SENDING / ENDED，可选", required = false) String executionStatus,
            @McpToolParam(description = "合约关键字，模糊匹配，可选", required = false) String symbol,
            @McpToolParam(description = "策略 ID，精确匹配，可选", required = false) String strategyId,
            @McpToolParam(description = "started_at 下限，可选", required = false) String startedAtFrom,
            @McpToolParam(description = "started_at 上限，可选", required = false) String startedAtTo,
            @McpToolParam(description = "ended_at 下限，可选", required = false) String endedAtFrom,
            @McpToolParam(description = "ended_at 上限，可选", required = false) String endedAtTo) {
        return backendClient.marketLookPage(
                pageNum,
                pageSize,
                executionStatus,
                symbol,
                strategyId,
                startedAtFrom,
                startedAtTo,
                endedAtFrom,
                endedAtTo);
    }

    @McpTool(
            name = "trade_look_market_look_get_by_id",
            description = "按 market_look.id（UUID）查询单条盯盘任务全部字段。")
    public Map<String, Object> marketLookGetById(
            @McpToolParam(description = "market_look.id", required = true) String marketLookId) {
        return backendClient.marketLookGetById(marketLookId);
    }

    @McpTool(
            name = "trade_look_market_look_delete",
            description = "按主键删除盯盘任务 market_look 一行。"
                    + " 必填：id（market_look.id，UUID）。"
                    + " 成功时 success=true 且 verifiedAbsent=true，表示数据库中该行已不存在（服务端在 DELETE 后再次查询校验）；"
                    + " 不存在时 success=false 与 HTTP 404；校验失败时 success=false 与错误说明。")
    public Map<String, Object> marketLookDelete(
            @McpToolParam(description = "market_look.id（UUID）", required = true) String id) {
        return backendClient.marketLookDelete(id);
    }

    @McpTool(
            name = "trade_look_market_look_sql",
            description = SQL_DESC)
    public Map<String, Object> marketLookSql(
            @McpToolParam(
                    description = "SELECT 语句，必须包含 `market_look`；用 ? 作为参数占位",
                    required = true) String sql,
            @McpToolParam(
                    description = "与 ? 顺序一致的参数列表，如 [\"RUNNING\"]；无占位符可传 []",
                    required = false) List<Object> params) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("sql", sql);
        body.put("params", params == null ? List.of() : params);
        return backendClient.marketLookSql(body);
    }
}
