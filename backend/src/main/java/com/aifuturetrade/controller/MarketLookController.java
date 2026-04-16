package com.aifuturetrade.controller;

import com.aifuturetrade.common.util.PageRequest;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.service.MarketLookDeleteOutcome;
import com.aifuturetrade.service.MarketLookService;
import com.aifuturetrade.service.dto.MarketLookDTO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 盯盘任务 market_look REST，供前端与 MCP 网关封装调用。
 */
@RestController
@RequestMapping("/api/market-look")
@Tag(name = "盯盘任务", description = "market_look 增删改查与状态更新")
public class MarketLookController {

    @Autowired
    private MarketLookService marketLookService;

    @GetMapping
    @Operation(summary = "全部盯盘任务列表（不分页）", description = "GET /api/market-look")
    public ResponseEntity<List<MarketLookDTO>> listAll() {
        return ResponseEntity.ok(marketLookService.listAll());
    }

    @GetMapping("/status/running")
    @Operation(summary = "活跃盯盘任务", description = "execution_status 为 RUNNING 或 SENDING（路径避免与 /{id} 冲突）")
    public ResponseEntity<List<MarketLookDTO>> listRunning() {
        return ResponseEntity.ok(marketLookService.listRunning());
    }

    @GetMapping("/page")
    @Operation(summary = "分页查询盯盘任务", description = "可选按 execution_status、symbol、strategy_id、started_at/ended_at 时间范围筛选")
    public ResponseEntity<?> page(
            @RequestParam(value = "pageNum", defaultValue = "1") Integer pageNum,
            @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize,
            @Parameter(description = "RUNNING | SENDING | ENDED")
            @RequestParam(value = "execution_status", required = false) String executionStatus,
            @RequestParam(value = "symbol", required = false) String symbol,
            @RequestParam(value = "strategy_id", required = false) String strategyId,
            @Parameter(description = "started_at 下限，ISO 或 yyyy-MM-dd HH:mm:ss")
            @RequestParam(value = "started_at_from", required = false) String startedAtFrom,
            @Parameter(description = "started_at 上限")
            @RequestParam(value = "started_at_to", required = false) String startedAtTo,
            @Parameter(description = "ended_at 下限")
            @RequestParam(value = "ended_at_from", required = false) String endedAtFrom,
            @Parameter(description = "ended_at 上限")
            @RequestParam(value = "ended_at_to", required = false) String endedAtTo) {
        PageRequest pr = new PageRequest();
        pr.setPageNum(pageNum);
        pr.setPageSize(pageSize);
        try {
            return ResponseEntity.ok(marketLookService.page(
                    pr,
                    executionStatus,
                    symbol,
                    strategyId,
                    parseOptionalDateTime(startedAtFrom, "started_at_from"),
                    parseOptionalDateTime(startedAtTo, "started_at_to"),
                    parseOptionalDateTime(endedAtFrom, "ended_at_from"),
                    parseOptionalDateTime(endedAtTo, "ended_at_to")));
        } catch (IllegalArgumentException e) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(err);
        }
    }

    @GetMapping("/{id}")
    @Operation(summary = "按 ID 查询盯盘任务")
    public ResponseEntity<MarketLookDTO> getById(@PathVariable("id") String id) {
        MarketLookDTO dto = marketLookService.getById(id);
        return dto != null ? ResponseEntity.ok(dto) : ResponseEntity.notFound().build();
    }

    @PostMapping
    @Operation(summary = "创建盯盘任务", description = "需关联 strategys 中 type=look 的策略")
    public ResponseEntity<Map<String, Object>> create(@RequestBody MarketLookDTO body) {
        try {
            MarketLookDTO created = marketLookService.create(body);
            Map<String, Object> res = new HashMap<>();
            res.put("id", created.getId());
            res.put("data", created);
            res.put("message", "created");
            return new ResponseEntity<>(res, HttpStatus.CREATED);
        } catch (IllegalArgumentException e) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(err);
        }
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新盯盘任务")
    public ResponseEntity<Map<String, Object>> update(@PathVariable("id") String id, @RequestBody MarketLookDTO body) {
        try {
            MarketLookDTO updated = marketLookService.update(id, body);
            Map<String, Object> res = new HashMap<>();
            res.put("data", updated);
            res.put("message", "updated");
            return ResponseEntity.ok(res);
        } catch (IllegalArgumentException e) {
            Map<String, Object> err = new HashMap<>();
            err.put("success", false);
            err.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(err);
        }
    }

    @PatchMapping("/{id}/status")
    @Operation(summary = "仅更新执行状态", description = "ENDED 时可省略 ended_at（服务端填当前时间）；RUNNING 时 ended_at 存占位以满足 NOT NULL")
    public ResponseEntity<Map<String, Object>> patchStatus(
            @PathVariable("id") String id,
            @RequestBody Map<String, Object> body) {
        try {
            String status = body != null && body.get("execution_status") != null
                    ? String.valueOf(body.get("execution_status"))
                    : null;
            LocalDateTime endedAt = parseEndedAt(body != null ? body.get("ended_at") : null);
            MarketLookDTO updated = marketLookService.patchStatus(id, status, endedAt);
            Map<String, Object> res = new HashMap<>();
            res.put("data", updated);
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

    private static LocalDateTime parseOptionalDateTime(String raw, String fieldName) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return parseEndedAt(raw);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException(fieldName + ": " + e.getMessage());
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

    @DeleteMapping("/{id}")
    @Operation(summary = "删除盯盘任务", description = "成功时 success=true 且 verifiedAbsent=true，表示 DELETE 后再次查询主键确认行已不存在")
    public ResponseEntity<Map<String, Object>> delete(@PathVariable("id") String id) {
        MarketLookDeleteOutcome outcome = marketLookService.delete(id);
        Map<String, Object> res = new HashMap<>();
        res.put("id", id);
        res.put("verifiedAbsent", outcome == MarketLookDeleteOutcome.VERIFIED_REMOVED);
        if (outcome == MarketLookDeleteOutcome.VERIFIED_REMOVED) {
            res.put("success", true);
            res.put("message", "deleted");
            return ResponseEntity.ok(res);
        }
        if (outcome == MarketLookDeleteOutcome.NOT_FOUND) {
            res.put("success", false);
            res.put("message", "not found");
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(res);
        }
        if (outcome == MarketLookDeleteOutcome.NO_ROWS_DELETED) {
            res.put("success", false);
            res.put("message", "delete affected zero rows");
            return ResponseEntity.status(HttpStatus.CONFLICT).body(res);
        }
        res.put("success", false);
        res.put("message", "delete executed but row still exists (verification failed)");
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(res);
    }
}
