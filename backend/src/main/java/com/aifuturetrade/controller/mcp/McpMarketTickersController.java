package com.aifuturetrade.controller.mcp;

import com.aifuturetrade.service.mcp.McpMarketTickersService;
import com.aifuturetrade.service.mcp.dto.McpMarketTickerSqlRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/mcp/market-tickers")
@Tag(name = "MCP-市场Ticker", description = "24_market_tickers 读库（无需 modelId）")
public class McpMarketTickersController {

    @Autowired
    private McpMarketTickersService marketTickersService;

    @GetMapping("/rows")
    @Operation(summary = "分页查询 ticker 原始行")
    public ResponseEntity<Map<String, Object>> rows(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size,
            @RequestParam(required = false) String symbol,
            @RequestParam(required = false) List<String> symbols,
            @RequestParam(required = false) String symbolsCsv,
            @RequestParam(required = false) String side,
            @RequestParam(required = false) Double minLastPrice,
            @RequestParam(required = false) Double maxLastPrice,
            @RequestParam(required = false) Double minPriceChangePercent,
            @RequestParam(required = false) Double maxPriceChangePercent,
            @RequestParam(required = false) Double minQuoteVolume,
            @RequestParam(required = false) Double maxQuoteVolume,
            @RequestParam(required = false) String orderBy,
            @RequestParam(required = false) Boolean orderAsc) {
        List<String> symList = mergeSymbolList(symbols, symbolsCsv);
        try {
            Map<String, Object> body = marketTickersService.queryRows(
                    page, size, symbol, symList, side,
                    minLastPrice, maxLastPrice,
                    minPriceChangePercent, maxPriceChangePercent,
                    minQuoteVolume, maxQuoteVolume,
                    orderBy, orderAsc);
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (Exception e) {
            return error(e);
        }
    }

    @GetMapping("/rows/count")
    @Operation(summary = "与 /rows 相同筛选条件下的总行数")
    public ResponseEntity<Map<String, Object>> rowsCount(
            @RequestParam(required = false) String symbol,
            @RequestParam(required = false) List<String> symbols,
            @RequestParam(required = false) String symbolsCsv,
            @RequestParam(required = false) String side,
            @RequestParam(required = false) Double minLastPrice,
            @RequestParam(required = false) Double maxLastPrice,
            @RequestParam(required = false) Double minPriceChangePercent,
            @RequestParam(required = false) Double maxPriceChangePercent,
            @RequestParam(required = false) Double minQuoteVolume,
            @RequestParam(required = false) Double maxQuoteVolume) {
        List<String> symList = mergeSymbolList(symbols, symbolsCsv);
        try {
            Map<String, Object> body = marketTickersService.countRows(
                    symbol, symList, side,
                    minLastPrice, maxLastPrice,
                    minPriceChangePercent, maxPriceChangePercent,
                    minQuoteVolume, maxQuoteVolume);
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (Exception e) {
            return error(e);
        }
    }

    @GetMapping("/snapshot")
    @Operation(summary = "每 symbol 最新一条，分页（全市场或限定 symbols）")
    public ResponseEntity<Map<String, Object>> snapshot(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size,
            @RequestParam(required = false) List<String> symbols,
            @RequestParam(required = false) String symbolsCsv) {
        List<String> symList = mergeSymbolList(symbols, symbolsCsv);
        try {
            Map<String, Object> body = marketTickersService.querySnapshot(page, size, symList);
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (Exception e) {
            return error(e);
        }
    }

    @GetMapping("/snapshot/count")
    @Operation(summary = "snapshot 分组总数")
    public ResponseEntity<Map<String, Object>> snapshotCount(
            @RequestParam(required = false) List<String> symbols,
            @RequestParam(required = false) String symbolsCsv) {
        List<String> symList = mergeSymbolList(symbols, symbolsCsv);
        try {
            Map<String, Object> body = marketTickersService.countSnapshot(symList);
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (Exception e) {
            return error(e);
        }
    }

    @GetMapping("/symbols")
    @Operation(summary = "全部 distinct symbol 列表")
    public ResponseEntity<Map<String, Object>> symbols() {
        try {
            Map<String, Object> body = marketTickersService.listAllSymbols();
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (Exception e) {
            return error(e);
        }
    }

    @GetMapping("/latest")
    @Operation(summary = "单 symbol 最新一行")
    public ResponseEntity<Map<String, Object>> latest(@RequestParam("symbol") String symbol) {
        try {
            Map<String, Object> body = marketTickersService.getLatestBySymbol(symbol);
            HttpStatus st = Boolean.TRUE.equals(body.get("success"))
                    ? HttpStatus.OK
                    : HttpStatus.BAD_REQUEST;
            return new ResponseEntity<>(body, st);
        } catch (Exception e) {
            return error(e);
        }
    }

    @PostMapping("/sql")
    @Operation(summary = "受控 SELECT（必须包含 24_market_tickers）")
    public ResponseEntity<Map<String, Object>> sql(@RequestBody McpMarketTickerSqlRequest req) {
        if (req == null) {
            Map<String, Object> bad = new HashMap<>();
            bad.put("success", false);
            bad.put("error", "请求体不能为空");
            return new ResponseEntity<>(bad, HttpStatus.BAD_REQUEST);
        }
        try {
            Map<String, Object> body = marketTickersService.executeValidatedSql(req.getSql(), req.getParams());
            return new ResponseEntity<>(body, HttpStatus.OK);
        } catch (IllegalArgumentException e) {
            Map<String, Object> bad = new HashMap<>();
            bad.put("success", false);
            bad.put("error", e.getMessage());
            return new ResponseEntity<>(bad, HttpStatus.BAD_REQUEST);
        } catch (Exception e) {
            return error(e);
        }
    }

    private static List<String> mergeSymbolList(List<String> symbols, String symbolsCsv) {
        List<String> out = new ArrayList<>();
        if (symbols != null) {
            for (String s : symbols) {
                if (s == null || s.isBlank()) {
                    continue;
                }
                String t = s.trim();
                if (t.contains(",")) {
                    for (String p : t.split(",")) {
                        if (!p.isBlank()) {
                            out.add(p.trim());
                        }
                    }
                } else {
                    out.add(t);
                }
            }
        }
        if (symbolsCsv != null && !symbolsCsv.isBlank()) {
            for (String p : symbolsCsv.split(",")) {
                if (!p.isBlank()) {
                    out.add(p.trim());
                }
            }
        }
        return out.isEmpty() ? null : out;
    }

    private static ResponseEntity<Map<String, Object>> error(Exception e) {
        Map<String, Object> resp = new HashMap<>();
        resp.put("success", false);
        resp.put("error", e.getMessage());
        return new ResponseEntity<>(resp, HttpStatus.INTERNAL_SERVER_ERROR);
    }
}
