package com.aifuturetrade.dao.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
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
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型ID（UUID格式）
     */
    @TableField("model_id")
    private String modelId;

    /**
     * 用户提示词
     */
    @TableField("user_prompt")
    private String userPrompt;

    /**
     * AI响应
     */
    @TableField("ai_response")
    private String aiResponse;

    /**
     * 思维链追踪
     */
    @TableField("cot_trace")
    private String cotTrace;

    /**
     * 对话类型（buy或sell）
     */
    @TableField("type")
    private String type;

    /**
     * 消耗的tokens数量
     */
    private Integer tokens;

    /**
     * 创建时间（数据库字段为timestamp）
     */
    @TableField("timestamp")
    private LocalDateTime timestamp;

}