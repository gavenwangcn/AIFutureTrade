package com.aifuturetrade.common.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 将请求体 JSON 解析失败转为统一错误体，避免仅依赖 Spring 默认 WARN 日志而客户端只看到 400 无结构信息。
 */
@RestControllerAdvice
public class HttpMessageNotReadableExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> handle(HttpMessageNotReadableException ex) {
        Throwable root = ex.getMostSpecificCause();
        String detail;
        if (root instanceof DateTimeParseException) {
            detail = "时间字段格式无效，请使用 ISO 本地时间（如 2026-04-16T15:03:05）、"
                    + "空格分隔（2026-04-16 15:03:05）或带偏移（2026-04-16T15:03:05+08:00）。原始错误: "
                    + root.getMessage();
        } else {
            detail = root != null && root.getMessage() != null ? root.getMessage() : ex.getMessage();
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("success", false);
        body.put("error", "请求体 JSON 无法解析: " + detail);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }
}
