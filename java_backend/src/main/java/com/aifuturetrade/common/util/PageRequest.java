package com.aifuturetrade.common.util;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

/**
 * 分页查询请求参数
 */
@Data
public class PageRequest implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     * 当前页码，默认为1
     */
    private Integer pageNum = 1;

    /**
     * 每页记录数，默认为10
     */
    private Integer pageSize = 10;

    /**
     * 排序字段
     */
    private String sortField;

    /**
     * 排序方向（asc或desc）
     */
    private String sortOrder = "asc";

}