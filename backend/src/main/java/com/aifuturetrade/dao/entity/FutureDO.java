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
 * 数据对象：合约配置
 * 对应表名：futures
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("futures")
public class FutureDO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 主键ID（UUID格式）
     */
    @TableId(value = "id", type = IdType.ASSIGN_UUID)
    private String id;

    /**
     * 交易对符号（如BTC）
     */
    private String symbol;

    /**
     * 合约符号（如BTCUSDT）
     */
    private String contractSymbol;

    /**
     * 合约名称（如比特币永续合约）
     */
    private String name;

    /**
     * 交易所（默认BINANCE_FUTURES）
     */
    private String exchange;

    /**
     * 相关链接
     */
    private String link;

    /**
     * 排序顺序
     */
    private Integer sortOrder;

    /**
     * 创建时间
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间
     * 注意：数据库表中不存在此字段，使用 @TableField(exist = false) 标记
     */
    @TableField(exist = false)
    private LocalDateTime updatedAt;

}