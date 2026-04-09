package com.aifuturetrade.trademcp.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "downstream")
public class DownstreamProperties {

    private Service backend = new Service();
    private Service binanceService = new Service();

    public Service getBackend() {
        return backend;
    }

    public void setBackend(Service backend) {
        this.backend = backend;
    }

    public Service getBinanceService() {
        return binanceService;
    }

    public void setBinanceService(Service binanceService) {
        this.binanceService = binanceService;
    }

    public static class Service {
        private String baseUrl;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }
    }
}

