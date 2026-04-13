package com.aifuturetrade.trademcp.client;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 将下游 HTTP 响应统一解析为 {@code Map<String, Object>}：
 * <ul>
 *   <li>2xx：解析 JSON 体；空体返回空 Map</li>
 *   <li>4xx/5xx：尽量解析 JSON（与 backend 约定的 {@code success/error} 或 Spring 默认错误体），
 *   不再仅因状态码抛异常，以便 MCP 工具把业务错误以 Map 形式返回</li>
 *   <li>连接/读超时等：捕获为 {@code success=false} 的 Map，避免长时间无反馈</li>
 * </ul>
 */
@Component
public class DownstreamJsonExchange {

    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public DownstreamJsonExchange(RestClient restClient, ObjectMapper objectMapper) {
        this.restClient = restClient;
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> get(String uriTemplate, Object... uriVariables) {
        try {
            return restClient.get().uri(uriTemplate, uriVariables).exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    public Map<String, Object> get(URI uri) {
        try {
            return restClient.get().uri(uri).exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    public Map<String, Object> postJson(String uriTemplate, Object body, Object... uriVariables) {
        try {
            return restClient.post()
                    .uri(uriTemplate, uriVariables)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    public Map<String, Object> postJson(URI uri, Object body) {
        try {
            return restClient.post()
                    .uri(uri)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    private Map<String, Object> readResponseAsMap(ClientHttpResponse response) throws IOException {
        String bodyText = StreamUtils.copyToString(response.getBody(), StandardCharsets.UTF_8);
        HttpStatusCode status = response.getStatusCode();

        if (!status.isError()) {
            if (bodyText == null || bodyText.isBlank()) {
                return new LinkedHashMap<>();
            }
            try {
                return objectMapper.readValue(bodyText, MAP_TYPE);
            } catch (Exception e) {
                Map<String, Object> wrap = new LinkedHashMap<>();
                wrap.put("success", true);
                wrap.put("data", bodyText);
                return wrap;
            }
        }

        return errorStatusToMap(status, bodyText);
    }

    private Map<String, Object> errorStatusToMap(HttpStatusCode status, String bodyText) {
        if (bodyText != null && !bodyText.isBlank()) {
            try {
                Map<String, Object> parsed = objectMapper.readValue(bodyText, MAP_TYPE);
                Map<String, Object> out = new LinkedHashMap<>(parsed);
                out.putIfAbsent("httpStatus", status.value());
                if (Boolean.TRUE.equals(out.get("success"))) {
                    out.put("success", false);
                    out.putIfAbsent("error", "下游返回 HTTP " + status.value());
                    return out;
                }
                out.putIfAbsent("success", false);
                if (!out.containsKey("error")) {
                    Object msg = out.get("message");
                    if (msg != null) {
                        out.put("error", String.valueOf(msg));
                    } else {
                        out.put("error", bodyText);
                    }
                }
                return out;
            } catch (Exception ignored) {
                // fall through
            }
        }
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("success", false);
        err.put("error", "HTTP " + status.value() + (bodyText != null && !bodyText.isBlank() ? ": " + bodyText : ""));
        err.put("httpStatus", status.value());
        return err;
    }

    private Map<String, Object> transportFailure(Throwable e) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("success", false);
        err.put("error", e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName());
        err.put("errorType", e.getClass().getSimpleName());
        return err;
    }
}
