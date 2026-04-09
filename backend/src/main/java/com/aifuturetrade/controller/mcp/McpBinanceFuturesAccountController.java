package com.aifuturetrade.controller.mcp;

import com.aifuturetrade.service.mcp.McpBinanceFuturesAccountService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/mcp/binance-futures/account")
@Tag(name = "MCP-币安期货-账户", description = "供 trade-mcp 调用的账户接口（必须传modelId）")
public class McpBinanceFuturesAccountController {

    @Autowired
    private McpBinanceFuturesAccountService accountService;

    @GetMapping("/balance")
    @Operation(summary = "获取期货账户余额（modelId）")
    public ResponseEntity<Map<String, Object>> balance(@RequestParam("modelId") String modelId) {
        Map<String, Object> resp = new HashMap<>();
        try {
            List<Map<String, Object>> data = accountService.balance(modelId);
            resp.put("success", true);
            resp.put("data", data);
            return new ResponseEntity<>(resp, HttpStatus.OK);
        } catch (Exception e) {
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/positions")
    @Operation(summary = "获取期货账户持仓（modelId）")
    public ResponseEntity<Map<String, Object>> positions(@RequestParam("modelId") String modelId) {
        Map<String, Object> resp = new HashMap<>();
        try {
            List<Map<String, Object>> data = accountService.positions(modelId);
            resp.put("success", true);
            resp.put("data", data);
            return new ResponseEntity<>(resp, HttpStatus.OK);
        } catch (Exception e) {
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/account-info")
    @Operation(summary = "获取期货账户信息（modelId）")
    public ResponseEntity<Map<String, Object>> accountInfo(@RequestParam("modelId") String modelId) {
        Map<String, Object> resp = new HashMap<>();
        try {
            Map<String, Object> data = accountService.accountInfo(modelId);
            resp.put("success", true);
            resp.put("data", data);
            return new ResponseEntity<>(resp, HttpStatus.OK);
        } catch (Exception e) {
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}

