package com.aifuturetrade.trademcp.client;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * 将下游 HTTP 响应统一解析为 {@code Map<String, Object>}：
 * <ul>
 *   <li>2xx：解析 JSON 体；空体返回空 Map</li>
 *   <li>4xx/5xx：尽量解析 JSON（与 backend 约定的 {@code success/error} 或 Spring 默认错误体），
 *   不再仅因状态码抛异常，以便 MCP 工具把业务错误以 Map 形式返回。
 *   Spring 6+ {@link RestClient} 对错误状态码可能先抛出 {@link RestClientResponseException}，需在 catch 中读取响应体再转 Map，否则会落到泛化 {@link #transportFailure}，MCP 端看不到下游 {@code error}。</li>
 *   <li>连接/读超时等：捕获为 {@code success=false} 的 Map，避免长时间无反馈</li>
 * </ul>
 */
@Component
public class DownstreamJsonExchange {

    private static final Logger log = LoggerFactory.getLogger(DownstreamJsonExchange.class);

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};

    private final RestClient restClient;

    public DownstreamJsonExchange(RestClient restClient) {
        this.restClient = restClient;
    }

    public Map<String, Object> get(String uriTemplate, Object... uriVariables) {
        try {
            return restClient.get().uri(uriTemplate, uriVariables).exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    public Map<String, Object> get(URI uri) {
        try {
            return restClient.get().uri(uri).exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
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
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
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
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    /** PATCH，JSON 请求体；响应解析规则与 POST 一致。 */
    public Map<String, Object> patchJson(URI uri, Object body) {
        Object payload = body != null ? body : Map.of();
        try {
            return restClient.patch()
                    .uri(uri)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    /** DELETE，响应体解析规则与 GET/POST 一致（含 4xx/5xx 转 Map）。 */
    public Map<String, Object> delete(URI uri) {
        try {
            return restClient.delete().uri(uri).exchange((request, response) -> readResponseAsMap(response));
        } catch (RestClientResponseException e) {
            return errorFromStatusException(e);
        } catch (RestClientException e) {
            return transportFailure(e);
        }
    }

    /** Spring {@link RestClient} 在 4xx/5xx 时可能直接抛异常，exchange 回调未执行，此处补读响应体。 */
    private Map<String, Object> errorFromStatusException(RestClientResponseException e) {
        String bodyText = "";
        try {
            bodyText = e.getResponseBodyAsString(StandardCharsets.UTF_8);
        } catch (Exception ignored) {
            // keep empty
        }
        log.debug("[downstream] HTTP {} 错误响应体: {}", e.getStatusCode().value(), bodyText);
        return errorStatusToMap(e.getStatusCode(), bodyText);
    }

    private Map<String, Object> readResponseAsMap(ClientHttpResponse response) throws IOException {
        String bodyText = StreamUtils.copyToString(response.getBody(), StandardCharsets.UTF_8);
        HttpStatusCode status = response.getStatusCode();

        if (!status.isError()) {
            if (bodyText == null || bodyText.isBlank()) {
                return new LinkedHashMap<>();
            }
            try {
                return JSON.readValue(bodyText, MAP_TYPE);
            } catch (Exception e) {
                log.warn("[downstream] 2xx 响应体非 JSON 或解析失败，以原文返回并附带解析错误（供模型排查）: {}", e.toString());
                Map<String, Object> wrap = new LinkedHashMap<>();
                wrap.put("success", true);
                wrap.put("data", bodyText);
                wrap.put("jsonParseWarning", ThrowableFormatter.formatForClient(e));
                return wrap;
            }
        }

        return errorStatusToMap(status, bodyText);
    }

    private Map<String, Object> errorStatusToMap(HttpStatusCode status, String bodyText) {
        if (bodyText != null && !bodyText.isBlank()) {
            try {
                Map<String, Object> parsed = JSON.readValue(bodyText, MAP_TYPE);
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
            } catch (Exception parseEx) {
                log.warn(
                        "[downstream] HTTP {} 错误体 JSON 解析失败，将退回原始正文；parseError={}",
                        status.value(),
                        parseEx.toString());
                Map<String, Object> err = new LinkedHashMap<>();
                err.put("success", false);
                err.put("httpStatus", status.value());
                err.put("error", "HTTP " + status.value() + (bodyText != null && !bodyText.isBlank() ? ": " + bodyText : ""));
                err.put("bodyParseError", ThrowableFormatter.formatForClient(parseEx));
                return err;
            }
        }
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("success", false);
        err.put("error", "HTTP " + status.value() + (bodyText != null && !bodyText.isBlank() ? ": " + bodyText : ""));
        err.put("httpStatus", status.value());
        return err;
    }

    private Map<String, Object> transportFailure(Throwable e) {
        log.warn("[downstream] 连接下游失败: {}", ThrowableFormatter.formatForClient(e));
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("success", false);
        err.put("error", ThrowableFormatter.formatForClient(e));
        err.put("errorType", e.getClass().getName());
        Throwable root = ThrowableFormatter.getRootCause(e);
        if (root != null && root != e) {
            err.put("rootCauseType", root.getClass().getName());
        }
        return err;
    }
}
