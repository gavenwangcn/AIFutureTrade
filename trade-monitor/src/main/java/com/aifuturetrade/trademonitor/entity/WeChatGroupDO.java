package com.aifuturetrade.trademonitor.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 微信群配置实体
 */
@Data
@TableName("wechat_groups")
public class WeChatGroupDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 群组名称
     */
    private String groupName;

    /**
     * 企业微信Webhook URL
     */
    private String webhookUrl;

    /**
     * 告警类型(逗号分隔)
     */
    private String alertTypes;

    /**
     * 是否启用
     */
    private Boolean isEnabled;

    /**
     * 描述
     */
    private String description;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;
}
