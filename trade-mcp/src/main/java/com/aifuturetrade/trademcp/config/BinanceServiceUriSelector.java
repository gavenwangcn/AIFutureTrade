package com.aifuturetrade.trademcp.config;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 与 Python {@code trade/common/config.py} 中 {@code BINANCE_SERVICE_LIST} 一致：
 * 支持多个 binance-service 根地址，按请求轮询使用。
 *
 * <p>优先级：环境变量 {@code BINANCE_SERVICE_LIST}（JSON 数组，元素含 {@code base_url}）；
 * 否则使用 {@code downstream.binance-service.base-urls}；再否则 {@code base-url} 单地址。
 */
@Component
public class BinanceServiceUriSelector {

    private static final JsonMapper MAPPER = JsonMapper.builder().build();

    private final List<String> urls;
    private int cursor;

    public BinanceServiceUriSelector(DownstreamProperties props) {
        this.urls = resolveUrls(props);
        if (urls.isEmpty()) {
            throw new IllegalStateException(
                    "未配置 binance-service 地址：请设置 downstream.binance-service.base-url / base-urls，"
                            + "或环境变量 BINANCE_SERVICE_LIST（JSON，与 trade 服务相同格式）");
        }
    }

    /**
     * 轮询返回下一个根 URL（不含尾部斜杠约定由调用方与路径拼接保证）。
     */
    public synchronized String nextBaseUrl() {
        String u = urls.get(cursor);
        cursor = (cursor + 1) % urls.size();
        return trimTrailingSlash(u);
    }

    public List<String> getAllBaseUrls() {
        return List.copyOf(urls);
    }

    static List<String> resolveUrls(DownstreamProperties props) {
        String env = System.getenv("BINANCE_SERVICE_LIST");
        if (env != null && !env.isBlank()) {
            List<String> fromEnv = parseBinanceServiceListJson(env.trim());
            if (!fromEnv.isEmpty()) {
                return fromEnv;
            }
        }
        DownstreamProperties.BinanceServiceConfig bs = props.getBinanceService();
        if (bs.getBaseUrls() != null && !bs.getBaseUrls().isEmpty()) {
            List<String> out = new ArrayList<>();
            for (String u : bs.getBaseUrls()) {
                if (u != null && !u.isBlank()) {
                    out.add(u.trim());
                }
            }
            if (!out.isEmpty()) {
                return out;
            }
        }
        if (bs.getBaseUrl() != null && !bs.getBaseUrl().isBlank()) {
            return List.of(bs.getBaseUrl().trim());
        }
        return List.of();
    }

    static List<String> parseBinanceServiceListJson(String json) {
        try {
            JsonNode root = MAPPER.readTree(json);
            if (!root.isArray()) {
                return List.of();
            }
            List<String> out = new ArrayList<>();
            for (JsonNode n : root) {
                if (n == null || !n.isObject()) {
                    continue;
                }
                String u = null;
                if (n.hasNonNull("base_url")) {
                    u = n.get("base_url").asText();
                } else if (n.hasNonNull("baseUrl")) {
                    u = n.get("baseUrl").asText();
                }
                if (u != null && !u.isBlank()) {
                    out.add(u.trim());
                }
            }
            return out;
        } catch (Exception e) {
            throw new IllegalArgumentException("BINANCE_SERVICE_LIST 不是合法 JSON 数组: " + e.getMessage(), e);
        }
    }

    private static String trimTrailingSlash(String u) {
        if (u == null || u.length() <= 1) {
            return u;
        }
        return u.endsWith("/") ? u.replaceAll("/+$", "") : u;
    }
}
