package com.aifuturetrade.controller.mcp;

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

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/mcp/market-look")
@Tag(name = "MCP-盯盘任务", description = "market_look 受控读库（无需 modelId）")
public class McpMarketLookController {

    @Autowired
    private McpMarketLookService mcpMarketLookService;

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
}
