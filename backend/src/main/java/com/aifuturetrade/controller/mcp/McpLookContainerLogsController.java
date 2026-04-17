package com.aifuturetrade.controller.mcp;

import com.aifuturetrade.service.DockerLogService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 盯盘 Docker 容器日志快照，供 MCP / 工具调用。容器名固定，仅可指定尾部行数。
 */
@RestController
@RequestMapping("/api/mcp/docker/look-container")
@Tag(name = "MCP-盯盘容器日志", description = "读取盯盘 Docker 容器最近若干行 stdout/stderr（非流式）")
public class McpLookContainerLogsController {

    /** 盯盘循环固定容器名（与 compose、动态创建一致）。 */
    public static final String LOOK_CONTAINER_NAME = "aifuturetrade-model-look-1";

    @Autowired
    private DockerLogService dockerLogService;

    @GetMapping("/logs")
    @Operation(
            summary = "最近 N 行盯盘容器日志（默认 1000）",
            description = "仅支持可选查询参数 tail（默认 1000，最大 5000）。容器固定为 aifuturetrade-model-look-1。")
    public ResponseEntity<Map<String, Object>> logs(@RequestParam(value = "tail", required = false) Integer tail) {
        int tailLines = tail == null ? 1000 : tail;
        Map<String, Object> body = dockerLogService.getContainerLogTail(LOOK_CONTAINER_NAME, tailLines);
        boolean ok = Boolean.TRUE.equals(body.get("success"));
        return new ResponseEntity<>(body, ok ? HttpStatus.OK : HttpStatus.BAD_REQUEST);
    }
}
