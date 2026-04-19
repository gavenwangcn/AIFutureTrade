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
                    + " 可选：strategy_name、execution_status（默认 RUNNING；创建时仅允许 RUNNING 或 ENDED）、signal_result、"
                    + "ended_at（计划截止时间；ISO 或 yyyy-MM-dd HH:mm:ss）。"
                    + " **开始时间无需传**：服务端固定为**上海时区**当前时间。**若省略 ended_at**（RUNNING）：服务端默认为「上海时区当前时间 + 24 小时」。"
                    + " 失败时 success=false 与 error 说明。")
    public Map<String, Object> marketLookCreate(
            @McpToolParam(description = "合约符号，如 BTC 或 BTCUSDT", required = true) String symbol,
            @McpToolParam(description = "策略 UUID（strategys.id，且 type 必须为 look）", required = true) String strategyId,
            @McpToolParam(description = "详情摘要，非空字符串", required = true) String detailSummary,
            @McpToolParam(description = "策略名称冗余，可选", required = false) String strategyName,
            @McpToolParam(description = "RUNNING 或 ENDED，默认 RUNNING", required = false) String executionStatus,
            @McpToolParam(description = "信号结果文本或 JSON 字符串，可选", required = false) String signalResult,
            @McpToolParam(
                    description = "计划结束/截止时间，可选；不传则 RUNNING 任务默认为当前时间+24h。格式：yyyy-MM-dd HH:mm:ss 或 ISO-8601",
                    required = false) String endedAt) {
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
        // 不传 started_at：backend 使用上海时区当前时间（MarketLookServiceImpl.create）
        if (endedAt != null && !endedAt.isEmpty()) {
            body.put("ended_at", endedAt);
        }
        return backendClient.marketLookCreate(body);
    }

    @McpTool(
            name = "trade_look_strategy_create_look",
            description = "新建策略，且 type 固定为盯盘 look。"
                    + " **标准流程（推荐，用于生成可执行盯盘代码）必填三项**：`name`、`validate_symbol`、`strategy_context`。"
                    + " 其中 **`validate_symbol` = 验证用合约 symbol（如 BTCUSDT）**，与前端「获取代码」一致，用于行情校验与试跑测试，**缺一则无法完成合法盯盘策略创建（含 AI 生成）**。"
                    + " 服务端用系统设置「策略API提供方」生成 strategy_code 并测试，**仅测试通过才落库**；勿传 strategy_code。"
                    + " **成功响应含 `strategy_code` / `test_result` 等**：须向用户展示完整代码并审阅逻辑；不满意则改 strategy_context 后再调 `trade_strategy_regenerate_code`。"
                    + " 例外：仅建无规则占位（不传 strategy_context）时可省略 validate_symbol，一般不推荐。"
                    + " type 固定为 look，无需传入。")
    public Map<String, Object> strategyCreateLook(
            @McpToolParam(description = "策略名称", required = true) String name,
            @McpToolParam(
                    description = "验证合约 symbol（*必传*）：与「获取代码」一致，用于行情校验与策略代码试跑，如 BTCUSDT。标准创建（含 strategy_context / AI 生成）时必填；仅建无说明空壳可不传",
                    required = false) String validateSymbol,
            @McpToolParam(description = "策略自然语言说明；标准流程下与 validate_symbol 同时为必填，供 AI 生成代码", required = false) String strategyContext) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", name);
        body.put("type", "look");
        if (validateSymbol != null && !validateSymbol.isEmpty()) {
            body.put("validate_symbol", validateSymbol);
        }
        if (strategyContext != null && !strategyContext.isEmpty()) {
            body.put("strategy_context", strategyContext);
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
                    + "detail_summary（摘要模糊）、started_at/ended_at 时间范围筛选（闭区间）。时间格式：yyyy-MM-dd HH:mm:ss 或 ISO-8601。"
                    + " 返回 PageResult：data 为行列表，total、pageNum、pageSize、totalPages。")
    public Map<String, Object> marketLookQueryPage(
            @McpToolParam(description = "页码，从 1 开始，默认 1", required = false) Integer pageNum,
            @McpToolParam(description = "每页条数，默认 10", required = false) Integer pageSize,
            @McpToolParam(description = "执行状态：RUNNING / SENDING / ENDED，可选", required = false) String executionStatus,
            @McpToolParam(description = "合约关键字，模糊匹配，可选", required = false) String symbol,
            @McpToolParam(description = "策略 ID，精确匹配，可选", required = false) String strategyId,
            @McpToolParam(description = "详情摘要关键字，模糊匹配，可选", required = false) String detailSummary,
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
                detailSummary,
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
            name = "trade_look_market_look_finish_by_id",
            description = "按 market_look.id 结束指定盯盘任务（置为 ENDED）。"
                    + " 除主键 id 外，下游请求体**仅**含结束时间字段 `ended_at`（可选；省略则服务端使用当前上海时间）。")
    public Map<String, Object> marketLookFinishById(
            @McpToolParam(description = "market_look.id（UUID）", required = true) String marketLookId,
            @McpToolParam(description = "任务结束时间（ended_at）。可省略或留空表示当前上海时间。", required = false)
                    String endedAt) {
        return backendClient.marketLookFinishById(marketLookId, endedAt);
    }

    @McpTool(
            name = "trade_look_market_look_set_plan_ended_at",
            description = "仅更新盯盘任务的计划/展示用结束时间字段 `ended_at`，**不**将任务标为 ENDED（不改 execution_status）。"
                    + " 用于执行中（RUNNING/SENDING）延长或缩短截止时间；与 `trade_look_market_look_finish_by_id`（结束任务）不同。"
                    + " 走 PUT /api/market-look/{id}，请求体仅含 ended_at。"
                    + " 时间格式：yyyy-MM-dd HH:mm:ss 或 ISO-8601；须不早于 started_at。")
    public Map<String, Object> marketLookSetPlanEndedAt(
            @McpToolParam(description = "market_look.id（UUID）", required = true) String marketLookId,
            @McpToolParam(description = "新的 ended_at（计划截止时间）", required = true) String endedAt) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ended_at", endedAt);
        return backendClient.marketLookUpdate(marketLookId, body);
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

    @McpTool(
            name = "trade_look_container_logs",
            description =
                    "读取**固定盯盘容器** Docker 日志（`aifuturetrade-model-look-1`）**最近若干行** stdout/stderr，"
                            + "用于分析策略执行输出、异常栈与优化策略代码。依赖 backend 能访问 Docker。"
                            + " **唯一参数**：尾部行数（默认 1000，最大 5000）。"
                            + " 成功时 `success=true`，`lines` 为字符串数组，`lineCount` 为行数；失败时 `success=false` 与 `error`。")
    public Map<String, Object> lookContainerLogs(
            @McpToolParam(description = "读取最近多少行日志，默认 1000，最大 5000", required = false) Integer tail) {
        return backendClient.lookContainerLogs(tail);
    }
}
