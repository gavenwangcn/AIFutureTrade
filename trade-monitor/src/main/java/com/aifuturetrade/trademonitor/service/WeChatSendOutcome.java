package com.aifuturetrade.trademonitor.service;

/**
 * 企微群 Webhook 发送结果（供落库合并 message 使用）
 */
public final class WeChatSendOutcome {

    private final boolean success;
    private final String errorDetail;

    private WeChatSendOutcome(boolean success, String errorDetail) {
        this.success = success;
        this.errorDetail = errorDetail != null ? errorDetail : "";
    }

    public static WeChatSendOutcome ok() {
        return new WeChatSendOutcome(true, "");
    }

    public static WeChatSendOutcome fail(String errorDetail) {
        return new WeChatSendOutcome(false, errorDetail);
    }

    public boolean isSuccess() {
        return success;
    }

    /**
     * 失败时的说明（多群时可能为多行）；成功时为空串
     */
    public String getErrorDetail() {
        return errorDetail;
    }
}
