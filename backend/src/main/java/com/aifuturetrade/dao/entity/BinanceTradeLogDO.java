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
 * 数据对象：币安交易日志
 * 对应表名：binance_trade_logs
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("binance_trade_logs")
public class BinanceTradeLogDO implements Serializable {

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
     * 对话ID（UUID格式，可为null）
     */
    @TableField("conversation_id")
    private String conversationId;

    /**
     * 交易ID（UUID格式，可为null）
     */
    @TableField("trade_id")
    private String tradeId;

    /**
     * 接口类型（test或real）
     */
    private String type;

    /**
     * 方法名称（如stop_loss_trade, take_profit_trade, market_trade, close_position_trade）
     */
    @TableField("method_name")
    private String methodName;

    /**
     * 调用接口的入参（JSON格式）
     */
    private String param;

    /**
     * 接口返回的内容（JSON格式，可为null）
     */
    @TableField("response_context")
    private String responseContext;

    /**
     * 接口返回状态码（如200, 4XX, 5XX等，可为null）
     */
    @TableField("response_type")
    private String responseType;

    /**
     * 接口返回状态不为200时记录相关的返回错误信息（可为null）
     */
    @TableField("error_context")
    private String errorContext;

    /**
     * 创建时间
     */
    @TableField("created_at")
    private LocalDateTime createdAt;

}

