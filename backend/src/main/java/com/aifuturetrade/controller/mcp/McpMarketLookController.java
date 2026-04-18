package com.aifuturetrade.controller.mcp;

import com.aifuturetrade.service.MarketLookService;
import com.aifuturetrade.service.dto.MarketLookDTO;
import com.aifuturetrade.service.mcp.McpMarketLookService;
import com.aifuturetrade.service.mcp.dto.McpMarketLookSqlRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/mcp/market-look")
@Tag(name = "MCP-盯盘任务", description = "market_look 受控读库（无需 modelId）")
public class McpMarketLookController {

    @Autowired
    private McpMarketLookService mcpMarketLookService;

    @Autowired
    private MarketLookService marketLookService;

    @PostMapping("/sql")
    @Operation(
            summary = "受控 SELECT（必须包含 market_look）",
            description = "列与表 market_look 一致：id, symbol, strategy_id, strategy_name, execution_status, "
                    + "signal_result, detail_summary, end_log, started_at, ended_at, created_at, updated_at")
    public ResponseEntity<Map<String, Object>> sql(@RequestBody McpMarketLookSqlRequest req) {
        if (req == null) {
            Map<String, Object> bad = new HashMap<>();
            bad.put("success", false);
            bad.put("error", "请求体不能为空");
            return new ResponseEntity<>(bad, HttpStatus.BAD_REQUEST);
        }
        try {
            Map<String, Object> body = mcpMarketLookService.executeValidatedSql(req.getSql(), req.getParams());
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (IllegalArgumentException e) {
            Map<String, Object> bad = new HashMap<>();
            bad.put("success", false);
            bad.put("error", e.getMessage());
            return new ResponseEntity<>(bad, HttpStatus.BAD_REQUEST);
        } catch (Exception e) {
            Map<String, Object> bad = new HashMap<>();
            bad.put("success", false);
            bad.put("error", e.getMessage());
            return new ResponseEntity<>(bad, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @PostMapping("/finish-running")
    @Operation(
            summary = "结束唯一执行中的盯盘任务",
            description = "当且仅当存在一条 RUNNING/SENDING 任务时将其置为 ENDED；请求体仅可含 ended_at（可选，默认当前上海时间）。"
                    + " 若 0 条或多条任务则返回 400。")
    public ResponseEntity<Map<String, Object>> finishRunning(@RequestBody(required = false) Map<String, Object> body) {
        try {
            LocalDateTime endedAt = parseEndedAt(body != null ? body.get("ended_at") : null);
            MarketLookDTO updated = marketLookService.finishSingleRunning(endedAt);
            Map<String, Object> res = new HashMap<>();
            res.put("data", updated);
            res.put("message", "ended");
            return ResponseEntity.ok(res);
        } catch (IllegalArgumentException e) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(err);
        } catch (Exception e) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(err);
        }
    }

    private static LocalDateTime parseEndedAt(Object raw) {
        if (raw == null) {
            return null;
        }
        String s = String.valueOf(raw).trim();
        if (s.isEmpty()) {
            return null;
        }
        try {
            return LocalDateTime.parse(s.replace(" ", "T"));
        } catch (DateTimeParseException ignored) {
            try {
                return LocalDateTime.parse(s, DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
            } catch (DateTimeParseException e) {
                throw new IllegalArgumentException("ended_at 格式无效: " + s);
            }
        }
    }
}
