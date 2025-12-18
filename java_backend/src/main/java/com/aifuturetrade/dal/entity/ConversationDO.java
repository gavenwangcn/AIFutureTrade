package com.aifuturetrade.dal.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 数据对象：AI对话记录
 * 对应表名：conversations
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("conversations")
public class ConversationDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /**
     * 模型ID
     */
    private Integer modelId;

    /**
     * 用户提示词
     */
    private String userPrompt;

    /**
     * AI响应
     */
    private String aiResponse;

    /**
     * 思维链追踪
     */
    private String cotTrace;

    /**
     * 对话类型（buy或sell）
     */
    private String conversationType;

    /**
     * 消耗的tokens数量
     */
    private Integer tokens;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

}