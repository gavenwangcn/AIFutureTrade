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
 * 数据对象：模型提示词配置
 * 对应表名：model_prompts
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("model_prompts")
public class ModelPromptDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 模型ID（UUID格式）
     */
    private String modelId;

    /**
     * 买入策略提示词
     */
    private String buyPrompt;

    /**
     * 卖出策略提示词
     */
    private String sellPrompt;

    /**
     * 更新时间
     */
    private LocalDateTime updatedAt;

}

