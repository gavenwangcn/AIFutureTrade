package com.aifuturetrade.controller;

import com.aifuturetrade.service.AccountService;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 控制器：账户管理
 */
@RestController
@RequestMapping("/api/accounts")
@Api(tags = "账户管理")
public class AccountController {

    @Autowired
    private AccountService accountService;

    /**
     * 查询所有账户信息
     */
    @GetMapping
    @ApiOperation("查询所有账户信息")
    public ResponseEntity<List<Map<String, Object>>> getAllAccounts() {
        List<Map<String, Object>> accounts = accountService.getAllAccounts();
        return new ResponseEntity<>(accounts, HttpStatus.OK);
    }

    /**
     * 添加新账户
     */
    @PostMapping
    @ApiOperation("添加新账户")
    public ResponseEntity<Map<String, Object>> addAccount(@RequestBody Map<String, Object> accountData) {
        Map<String, Object> result = accountService.addAccount(accountData);
        return new ResponseEntity<>(result, HttpStatus.CREATED);
    }

    /**
     * 删除账户
     */
    @DeleteMapping("/{accountAlias}")
    @ApiOperation("删除账户")
    public ResponseEntity<Map<String, Object>> deleteAccount(@PathVariable String accountAlias) {
        Map<String, Object> result = accountService.deleteAccount(accountAlias);
        return new ResponseEntity<>(result, HttpStatus.OK);
    }
}

