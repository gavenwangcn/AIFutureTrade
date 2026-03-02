package com.aifuturetrade.trademonitor.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 告警记录实体
 */
@Data
@TableName("alert_records")
public class AlertRecordDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 告警类型
     */
    private String alertType;

    /**
     * 服务名称
     */
    private String serviceName;

    /**
     * 严重程度
     */
    private String severity;

    /**
     * 告警标题
     */
    private String title;

    /**
     * 告警详细信息
     */
    private String message;

    /**
     * 状态
     */
    private String status;

    /**
     * 已执行的处置动作
     */
    private String actionTaken;

    /**
     * 是否已发送微信通知
     */
    private Boolean wechatSent;

    /**
     * 微信通知发送时间
     */
    private LocalDateTime wechatSentAt;

    /**
     * 解决时间
     */
    private LocalDateTime resolvedAt;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;
}
