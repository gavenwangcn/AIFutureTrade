package com.aifuturetrade.trademcp.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;

@ConfigurationProperties(prefix = "downstream")
public class DownstreamProperties {

    private Service backend = new Service();
    private BinanceServiceConfig binanceService = new BinanceServiceConfig();

    public Service getBackend() {
        return backend;
    }

    public void setBackend(Service backend) {
        this.backend = backend;
    }

    public BinanceServiceConfig getBinanceService() {
        return binanceService;
    }

    public void setBinanceService(BinanceServiceConfig binanceService) {
        this.binanceService = binanceService;
    }

    /** Java backend（账号/下单，modelId），通常单实例即可 */
    public static class Service {
        private String baseUrl;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }
    }

    /**
     * binance-service（行情/K 线等）：支持多地址轮询，与 trade 的 BINANCE_SERVICE_LIST 对齐。
     */
    public static class BinanceServiceConfig {
        /**
         * 单地址（兼容旧配置）；与 base-urls 二选一或同时存在时由 {@link BinanceServiceUriSelector} 合并解析。
         */
        private String baseUrl;

        /**
         * 多实例根 URL 列表，例如负载均衡的多台 binance-service。
         */
        private List<String> baseUrls = new ArrayList<>();

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public List<String> getBaseUrls() {
            return baseUrls;
        }

        public void setBaseUrls(List<String> baseUrls) {
            this.baseUrls = baseUrls;
        }
    }
}
