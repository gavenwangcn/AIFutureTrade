package com.aifuturetrade.controller.mcp;

import com.aifuturetrade.service.mcp.McpBinanceFuturesOrderService;
import com.aifuturetrade.service.mcp.dto.McpOrderCancelRequest;
import com.aifuturetrade.service.mcp.dto.McpOrderCreateRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/mcp/binance-futures/order")
@Tag(name = "MCP-币安期货-订单", description = "供 trade-mcp 调用的订单接口（必须传modelId）")
public class McpBinanceFuturesOrderController {

    @Autowired
    private McpBinanceFuturesOrderService orderService;

    @PostMapping("/create")
    @Operation(summary = "创建订单（modelId）")
    public ResponseEntity<Map<String, Object>> create(
            @RequestParam("modelId") String modelId,
            @Valid @RequestBody McpOrderCreateRequest request) {
        try {
            Map<String, Object> result = orderService.create(modelId, request);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> resp = new HashMap<>();
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @PostMapping("/cancel")
    @Operation(summary = "撤销订单（modelId）")
    public ResponseEntity<Map<String, Object>> cancel(
            @RequestParam("modelId") String modelId,
            @Valid @RequestBody McpOrderCancelRequest request) {
        try {
            Map<String, Object> result = orderService.cancel(modelId, request);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> resp = new HashMap<>();
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/get")
    @Operation(summary = "查询订单（modelId）")
    public ResponseEntity<Map<String, Object>> get(
            @RequestParam("modelId") String modelId,
            @RequestParam("symbol") String symbol,
            @RequestParam(value = "orderId", required = false) Long orderId,
            @RequestParam(value = "origClientOrderId", required = false) String origClientOrderId) {
        try {
            Map<String, Object> result = orderService.get(modelId, symbol, orderId, origClientOrderId);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> resp = new HashMap<>();
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @GetMapping("/open-orders")
    @Operation(summary = "查询当前挂单（modelId）")
    public ResponseEntity<Map<String, Object>> openOrders(
            @RequestParam("modelId") String modelId,
            @RequestParam(value = "symbol", required = false) String symbol) {
        Map<String, Object> resp = new HashMap<>();
        try {
            List<Map<String, Object>> data = orderService.openOrders(modelId, symbol);
            resp.put("success", true);
            resp.put("data", data);
            return new ResponseEntity<>(resp, HttpStatus.OK);
        } catch (Exception e) {
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    @PostMapping("/sell-position")
    @Operation(summary = "一键卖出持仓（modelId）")
    public ResponseEntity<Map<String, Object>> sellPosition(
            @RequestParam("modelId") String modelId,
            @RequestParam("symbol") String symbol) {
        try {
            Map<String, Object> result = orderService.sellPosition(modelId, symbol);
            return new ResponseEntity<>(result, HttpStatus.OK);
        } catch (Exception e) {
            Map<String, Object> resp = new HashMap<>();
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
}

