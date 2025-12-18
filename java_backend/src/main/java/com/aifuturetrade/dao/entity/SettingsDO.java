package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：系统设置
 * 对应表名：settings
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("settings")
public class SettingsDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /**
     * 买入交易频率（分钟）
     */
    private Integer buyFrequencyMinutes;

    /**
     * 卖出交易频率（分钟）
     */
    private Integer sellFrequencyMinutes;

    /**
     * 手续费率
     */
    private Double tradingFeeRate;

    /**
     * 是否显示系统提示（1：是，0：否）
     */
    private Boolean showSystemPrompt;

    /**
     * AI对话显示数量限制
     */
    private Integer conversationLimit;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}

